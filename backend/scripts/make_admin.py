"""Grant or revoke platform admin (staff dashboard) for a user who has signed in once.

uv run python -m scripts.make_admin someone@example.com [--revoke]
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User


async def main(email: str, revoke: bool) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise SystemExit(f"No user with email {email}. They need to sign in once first.")
        user.is_platform_admin = not revoke
        await session.commit()
        print(f"{email}: platform admin = {user.is_platform_admin}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1], "--revoke" in sys.argv[2:]))
