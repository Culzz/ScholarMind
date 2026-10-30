"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    applications,
    assistant,
    auth,
    changes,
    eligibility,
    health,
    planning,
    profile,
    rule_review,
    scholarships,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(profile.router)
router.include_router(applications.router)
router.include_router(applications.tasks_router)
router.include_router(assistant.router)
router.include_router(eligibility.router)
router.include_router(scholarships.router)
router.include_router(planning.router)
router.include_router(changes.router)
router.include_router(changes.admin_router)
router.include_router(rule_review.admin_router)
