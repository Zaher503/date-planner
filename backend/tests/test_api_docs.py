import re
from pathlib import Path

from app.main import app

DOC = Path(__file__).resolve().parents[2] / "docs" / "API.md"
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
# Routes the doc leaves out on purpose
SKIP = set()  # the app shell and tile routes are hidden from the schema, so nothing else to skip


def norm(path: str) -> str:
    """Parameter names differ between code and doc, so compare with a placeholder."""
    return re.sub(r"\{[^}]*\}", "{}", path.split("?")[0])


def code_routes() -> set[str]:
    """Every route in the OpenAPI schema (FastAPI keeps included routers lazy, so app.routes is not enough)."""
    found = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in METHODS:
                found.add(f"{method.upper()} {norm(path)}")
    return found - SKIP


def doc_routes() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    return {f"{m} {norm(p)}" for m, p in re.findall(r"`(GET|POST|PUT|PATCH|DELETE) (/[^\s`]*)", text)}


def test_every_route_is_in_the_api_doc():
    missing = sorted(code_routes() - doc_routes())
    assert not missing, "docs/API.md does not list: " + ", ".join(missing)


def test_the_check_sees_routes():
    assert "POST /api/ui/add" in code_routes() and "GET /api/items/{}/{}" in code_routes()
