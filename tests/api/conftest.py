"""Shared API-test fixtures.

Rate-limit budgets are process-global; reset them between tests so a module's
remaining budget is never an accident of what ran before it.
"""

from __future__ import annotations

import pytest

from app.core.rate_limit import reset_rate_limits


@pytest.fixture(autouse=True)
def _fresh_rate_budgets():
    reset_rate_limits()
    yield
    reset_rate_limits()
