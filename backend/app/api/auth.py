"""Who is calling.

Caddy runs Authentik forward_auth and passes X-Authentik-Username. That header is
only trusted when the TCP peer is the NAS (TRUSTED_PROXY); anything else on the LAN
could set it. The Shortcut endpoint uses a shared key instead.
"""
import hmac

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db

USER_HEADER = "x-authentik-username"
NAME_HEADER = "x-authentik-name"


def _peer(request: Request) -> str:
    return request.client.host if request.client else ""


def username_from_request(request: Request) -> str | None:
    s = get_settings()
    if s.dev_user:
        return s.dev_user
    if _peer(request) != s.trusted_proxy:
        return None
    return request.headers.get(USER_HEADER) or None


def upsert_user(db: Session, username: str, display_name: str | None = None) -> User:
    db.execute(insert(User).values(username=username, display_name=display_name)
               .on_conflict_do_nothing(index_elements=["username"]))
    user = db.scalars(select(User).where(User.username == username)).one()
    if display_name and user.display_name != display_name:
        user.display_name = display_name
    db.commit()
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    username = username_from_request(request)
    if not username:
        raise HTTPException(403, "not signed in through Authentik")
    return upsert_user(db, username, request.headers.get(NAME_HEADER))


def require_key(x_dates_key: str = Header(default="")) -> None:
    key = get_settings().dates_key
    if not key or not hmac.compare_digest(x_dates_key.encode(), key.encode()):
        raise HTTPException(401, "bad or missing X-Dates-Key")
