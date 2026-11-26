"""Resolve the signed-in user from the request.

Production uses Google Identity Platform (Firebase Auth): the frontend signs the
user in and sends the ID token as `Authorization: Bearer <token>`. We verify it
and create the user (plus a personal workspace) on first sight.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models import User
from app.services.workspaces import ensure_personal_workspace


@dataclass
class Identity:
    uid: str
    email: str
    name: str | None = None
    picture: str | None = None


_firebase_app = None


def _verify_firebase_token(token: str, settings: Settings) -> Identity:
    global _firebase_app
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if _firebase_app is None:
        options = {"projectId": settings.gcp_project_id} if settings.gcp_project_id else None
        _firebase_app = firebase_admin.initialize_app(options=options)
    try:
        claims = fb_auth.verify_id_token(token, app=_firebase_app, check_revoked=False)
    except Exception as exc:  # invalid, expired, wrong project...
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    email = claims.get("email")
    if not email or not claims.get("email_verified", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A verified email address is required")
    return Identity(
        uid=claims["uid"],
        email=email.lower(),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


async def get_identity(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Identity:
    if settings.auth_mode == "dev":
        if not x_dev_user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Dev-User header")
        email = x_dev_user.strip().lower()
        return Identity(uid=f"dev:{email}", email=email, name=email.split("@")[0])

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return _verify_firebase_token(authorization.split(" ", 1)[1], settings)


async def get_current_user(
    identity: Identity = Depends(get_identity),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.scalar(select(User).where(User.auth_uid == identity.uid))
    if user is None:
        user = User(
            auth_uid=identity.uid,
            email=identity.email,
            display_name=identity.name,
            photo_url=identity.picture,
        )
        session.add(user)
        await session.flush()
        await ensure_personal_workspace(session, user)
        await session.commit()
    elif user.email != identity.email:
        user.email = identity.email
        await session.commit()
    if user.is_disabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return user
