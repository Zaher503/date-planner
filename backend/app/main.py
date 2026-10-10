"""FastAPI app: JSON API, and later the built UI, tiles and calendar feeds."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api import add, health, items, map, meta, review
from app.api.auth import current_user
from app.db.models import AppSettings, User
from app.db.session import SessionLocal, get_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        db.execute(insert(AppSettings).values(id=1).on_conflict_do_nothing(index_elements=["id"]))
        db.commit()
    yield


app = FastAPI(title="Date Planner", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(add.router)
app.include_router(health.router)
app.include_router(review.router)
app.include_router(meta.router)
app.include_router(map.router)
app.include_router(items.router)


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "display_name": user.display_name}
