"""Seed dashboard reviewer accounts: 1 local volunteer + 3 domain experts.

Creates the `dashboard_users` login rows AND the matching profile rows
(`local_volunteers` / `domain_experts`, one expert per domain).

Run:
    uv run python scripts/seed_reviewers.py

Idempotent: skips a user whose email already exists and only creates a
profile row if it's missing, so it's safe to re-run.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the repo root importable when run as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import crud.dashboard_user as crud_user
import crud.expert as crud_expert
import crud.volunteer as crud_volunteer

# Shared demo password for every seeded account (change in a real deployment).
DEMO_PASSWORD = "pucho1234"

VOLUNTEER = {"name": "Gaurav", "email": "gaurav@pucho.org"}

EXPERTS = [
    {
        "name": "Hema Joshi",
        "email": "hema@pucho.org",
        "domain": "legal",
        "highest_education": "masters",
        "work_status": "working",
    },
    {
        "name": "Dr. Anjali Mehta",
        "email": "anjali@pucho.org",
        "domain": "healthcare",
        "highest_education": "doctorate",
        "work_status": "working",
    },
    {
        "name": "Rakesh Iyer",
        "email": "rakesh@pucho.org",
        "domain": "financial",
        "highest_education": "masters",
        "work_status": "working",
    },
]


async def _ensure_user(name: str, email: str, role: str):
    existing = await crud_user.get_by_email(email)
    if existing is not None:
        print(f"  user exists:  {email}  (role={existing.role})")
        return existing
    user = await crud_user.create_with_email(
        name=name, email=email, password=DEMO_PASSWORD, role=role
    )
    print(f"  user created: {email}  (role={role})")
    return user


async def seed() -> None:
    print("Local volunteer:")
    vol_user = await _ensure_user(
        VOLUNTEER["name"], VOLUNTEER["email"], "local_volunteer"
    )
    if await crud_volunteer.get_by_user_id(vol_user.id) is None:
        await crud_volunteer.create(user_id=vol_user.id, name=VOLUNTEER["name"])
        print("    volunteer profile created")
    else:
        print("    volunteer profile exists")

    print("\nDomain experts:")
    for e in EXPERTS:
        user = await _ensure_user(e["name"], e["email"], "expert")
        if await crud_expert.get_for_user_domain(user.id, e["domain"]) is None:
            await crud_expert.create(
                user_id=user.id,
                domain=e["domain"],
                name=e["name"],
                highest_education=e["highest_education"],
                work_status=e["work_status"],
                verified=True,
            )
            print(f"    expert profile created: {e['domain']}")
        else:
            print(f"    expert profile exists:  {e['domain']}")

    print("\n" + "=" * 48)
    print("Dashboard login credentials")
    print(f"  password (all accounts): {DEMO_PASSWORD}")
    print(f"  {VOLUNTEER['email']:24} local_volunteer")
    for e in EXPERTS:
        print(f"  {e['email']:24} expert ({e['domain']})")
    print("=" * 48)


if __name__ == "__main__":
    asyncio.run(seed())
