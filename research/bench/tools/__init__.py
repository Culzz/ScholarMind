"""Tooling for the ScholarBench-Africa benchmark release.

Modules
-------
``redact``
    Release-file redaction check: no page bodies, no unapproved URLs, no
    evidence markers.
``publish``
    Release builder: schema validation, redaction check, SHA-256 hashes and
    the ``dist/`` artifact.

Both modules use the standard library only.
"""

from __future__ import annotations

__all__ = ["publish", "redact"]
