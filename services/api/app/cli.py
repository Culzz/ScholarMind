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
import sys
from typing import Sequence

from sqlalchemy import text

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

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
