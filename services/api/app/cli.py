"""Operator command line.

Administrators are provisioned here, never through public registration:

    PYTHONPATH="services/api:." python -m app.cli create-admin --email ops@example.org
    PYTHONPATH="services/api:." python -m app.cli list-admins
    PYTHONPATH="services/api:." python -m app.cli revoke-sessions --email ops@example.org

The password is read from the terminal unless ``--password`` is supplied, which
keeps it out of shell history and process listings.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any, Sequence

from sqlalchemy import text

from app.core.errors import ApiError
from app.core.security import Role, hash_password
from app.db.session import get_engine

MIN_PASSWORD_LENGTH = 10


def _read_password(supplied: str | None) -> str:
    password = supplied or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


def create_admin(email: str, password: str, full_name: str | None = None) -> str:
    """Create an administrator, or promote an existing account. Idempotent."""
    normalised = email.strip().lower()
    with get_engine().begin() as connection:
        existing = connection.execute(
            text("SELECT id::text, role FROM users WHERE email = :email"),
            {"email": normalised},
        ).first()

        if existing:
            connection.execute(
                text("UPDATE users SET role = 'admin', updated_at = now() WHERE id = CAST(:id AS uuid)"),
                {"id": existing[0]},
            )
            return f"promoted existing account {normalised} from {existing[1]} to admin"

        connection.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, full_name, role)
                VALUES (gen_random_uuid(), :email, :password_hash, :full_name, 'admin')
                """
            ),
            {
                "email": normalised,
                "password_hash": hash_password(password),
                "full_name": full_name,
            },
        )
    return f"created administrator {normalised}"


def list_admins() -> list[str]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT email::text FROM users
                WHERE role = :role AND is_active
                ORDER BY email
                """
            ),
            {"role": Role.ADMIN.value},
        ).fetchall()
    return [row[0] for row in rows]


def revoke_sessions(email: str) -> int:
    """Revoke every refresh-token family belonging to an account."""
    with get_engine().begin() as connection:
        user = connection.execute(
            text("SELECT id::text FROM users WHERE email = :email"),
            {"email": email.strip().lower()},
        ).first()
        if user is None:
            raise SystemExit(f"no account for {email}")
        result = connection.execute(
            text(
                """
                UPDATE refresh_tokens SET revoked_at = now()
                WHERE user_id = CAST(:user AS uuid) AND revoked_at IS NULL
                """
            ),
            {"user": user[0]},
        )
        return result.rowcount or 0


def draft_rules_cmd(limit: int, scholarship_id: str | None, dry_run: bool) -> dict[str, Any]:
    """Run the LLM drafting pass over eligibility-looking chunks."""
    from app.core.config import get_settings
    from app.db.session import get_session_factory
    from app.services.rule_drafting import draft_rules

    settings = get_settings()
    with get_session_factory()() as session:  # type: ignore[call-arg]
        return draft_rules(
            session,
            settings,
            limit_chunks=limit,
            scholarship_id=scholarship_id,
            dry_run=dry_run,
        )


def list_rule_candidates(status: str, limit: int) -> list[dict[str, Any]]:
    from app.db.session import get_session_factory

    with get_session_factory()() as session, session.begin():
        rows = session.execute(
            text(
                """
                SELECT id::text, cycle_id::text AS cycle, kind, subject, operator, value,
                       rule_text, span_text, status, drafted_by
                FROM rule_candidates
                WHERE status = :status OR :status = 'all'
                ORDER BY created_at
                LIMIT :limit
                """
            ),
            {"status": status, "limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


def review_decide(candidate_id: str, decision: str, note: str | None) -> dict[str, Any]:
    """Approve or reject a candidate. Approval re-validates before inserting."""
    from app.api.v1.rule_review import RejectRequest, ApproveRequest, _candidate
    from app.api.v1.rule_review import approve_rule_candidate, reject_rule_candidate
    from app.db.session import get_session_factory

    with get_session_factory()() as session:  # type: ignore[call-arg]
        # Confirm the candidate exists before building the response object.
        _candidate(session, candidate_id)
        if decision == "approved":
            outcome = approve_rule_candidate(
                candidate_id, ApproveRequest(note=note), session=session, user={"sub": "cli"}
            )
        else:
            outcome = reject_rule_candidate(
                candidate_id, RejectRequest(note=note), session=session, user={"sub": "cli"}
            )
        return outcome


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ScholarMind operator commands")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="create or promote an administrator")
    create.add_argument("--email", required=True)
    create.add_argument("--password", default=None, help="omit to be prompted")
    create.add_argument("--full-name", default=None)

    sub.add_parser("list-admins", help="list active administrators")

    revoke = sub.add_parser("revoke-sessions", help="revoke an account's refresh tokens")
    revoke.add_argument("--email", required=True)

    draft = sub.add_parser("draft-rules", help="draft rule candidates with the configured LLM")
    draft.add_argument("--limit", type=int, default=40, help="maximum chunks to read (each chunk costs one API call)")
    draft.add_argument("--scholarship", default=None, help="restrict drafting to one scholarship id")
    draft.add_argument("--dry-run", action="store_true", help="call the LLM and report, but write nothing")

    review = sub.add_parser("review-rules", help="list or decide rule candidates")
    review.add_argument("--status", default="proposed", choices=["proposed", "approved", "rejected", "all"])
    review.add_argument("--limit", type=int, default=25)
    review.add_argument("--approve", default=None, metavar="CANDIDATE_ID")
    review.add_argument("--reject", default=None, metavar="CANDIDATE_ID")
    review.add_argument("--note", default=None, help="reviewer note for approve/reject")

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        print(create_admin(args.email, _read_password(args.password), args.full_name))
        return 0
    if args.command == "list-admins":
        for email in list_admins():
            print(email)
        return 0
    if args.command == "revoke-sessions":
        print(f"revoked {revoke_sessions(args.email)} refresh token(s)")
        return 0
    if args.command == "draft-rules":
        try:
            report = draft_rules_cmd(args.limit, args.scholarship, args.dry_run)
        except RuntimeError as exc:
            print(f"draft-rules: {exc}")
            return 2
        prefix = "[dry run] " if report["dry_run"] else ""
        print(
            f"{prefix}chunks={report['chunks_seen']} "
            f"candidates={report['candidates_inserted']} "
            f"rejected={report['candidates_rejected']} "
            f"parse_failures={report['parse_failures']} "
            f"no_cycle={report['chunks_without_current_cycle']}"
        )
        for rejection in report["rejections"][:10]:
            print(f"  rejected: {json.dumps(rejection, default=str)[:200]}")
        return 0
    if args.command == "review-rules":
        if args.approve and args.reject:
            print("review-rules: choose either --approve or --reject, not both")
            return 2
        if args.approve or args.reject:
            try:
                outcome = review_decide(
                    args.approve or args.reject,
                    "approved" if args.approve else "rejected",
                    args.note,
                )
            except ApiError as exc:
                print(f"{args.approve or args.reject}: {exc.code}: {exc.message}")
                if exc.detail:
                    print(json.dumps(exc.detail, indent=1))
                return 2
            print(f"{outcome['id']}: {outcome['status']}")
            if "rule_id" in outcome:
                print(f"  eligibility rule: {outcome['rule_id']}")
            return 0
        for row in list_rule_candidates(args.status, args.limit):
            value = json.dumps(row["value"])
            print(
                f"{row['id']} [{row['status']}] {row['kind']}/{row['subject']} "
                f"{row['operator']}={value} by={row['drafted_by']}"
            )
            print(f"  quote: {row['span_text'][:140]}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
