"""Saved import cases: replay the read and prepare steps of the pipeline offline, or record a case from a link.

A case is a folder (see backend/tests/replay/README.md):
    case.json      kind, url, caption, now, and the pages the web returned
    pages/*.html   the saved pages
    model.json     the saved model answers, in the order they were asked
    expected.json  the prepared hints

    python -m app.replay record <url> <case-folder>   save a case from a live event page link
    python -m app.replay show <case-folder>           print what a saved case produces now
"""
import json
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app import browser, jobs
from app.ingest import pipeline, pricing
from app.llm import extract as llm_extract

# Where each part of the pipeline asks the web or the model; modules import these by name
MODELS = {"extract": llm_extract, "pricing": pricing}
SYSTEM_KEY = 80  # how much of the system prompt identifies a saved answer


@dataclass
class Case:
    kind: str
    url: str | None
    caption: str | None
    now: datetime
    pages: dict[str, dict] = field(default_factory=dict)  # requested url -> {final, file} | {status} | {error}
    files: dict[str, str] = field(default_factory=dict)  # page file name -> html
    model: list[dict] = field(default_factory=list)  # {module, system, answer}
    expected: list[dict] | None = None


def load_case(folder: Path) -> Case:
    folder = Path(folder)
    meta = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    pages = meta.get("pages", {})
    files = {p["file"]: (folder / "pages" / p["file"]).read_text(encoding="utf-8")
             for p in pages.values() if "file" in p}
    model_file, expected_file = folder / "model.json", folder / "expected.json"
    return Case(
        kind=meta["kind"], url=meta.get("url"), caption=meta.get("caption"),
        now=datetime.fromisoformat(meta["now"]), pages=pages, files=files,
        model=json.loads(model_file.read_text(encoding="utf-8")) if model_file.exists() else [],
        expected=json.loads(expected_file.read_text(encoding="utf-8")) if expected_file.exists() else None)


def save_case(case: Case, folder: Path) -> None:
    folder = Path(folder)
    (folder / "pages").mkdir(parents=True, exist_ok=True)
    for name, html in case.files.items():
        (folder / "pages" / name).write_text(html, encoding="utf-8", newline="\n")
    meta = {"kind": case.kind, "url": case.url, "caption": case.caption, "now": case.now.isoformat(),
            "pages": case.pages}
    _write(folder / "case.json", meta)
    _write(folder / "model.json", case.model)
    if case.expected is not None:
        _write(folder / "expected.json", case.expected)


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def hint_dict(h) -> dict:
    """A hint as plain JSON: only the fields that carry something."""
    out = {}
    for k, v in asdict(h).items():
        if v is None or v is False or v == [] or v == "":
            continue
        out[k] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


class NoDb:
    def commit(self):
        pass


def prepare_link(kind: str, url: str | None, caption: str | None, now: datetime) -> list[dict]:
    """Read and prepare one link with no database. The web and the model must already be stubbed."""
    src = SimpleNamespace(kind=kind, url=url, caption=caption, raw={}, title=None, transcript=None,
                          fetched_at=None, id="replay")
    job = SimpleNamespace(id=0, payload={})
    g = pipeline.read_link(NoDb(), job, src)
    return [hint_dict(h) for h in pipeline.prepare(NoDb(), job, src, g, now)]


class Tape:
    """Answers the pipeline from a saved case, and remembers what it could not answer."""
    def __init__(self, case: Case):
        self.case = case
        self.unused = list(range(len(case.model)))
        self.misses: list[str] = []

    def fetch(self, url: str, client=None):
        page = self.case.pages.get(url)
        if page is None:
            self.misses.append(f"fetch {url}")
            raise AssertionError(f"page not in the saved case: {url}")
        if "file" in page:
            return page["final"], self.case.files[page["file"]]
        if "status" in page:
            raise httpx.HTTPStatusError("saved error", request=httpx.Request("GET", url),
                                        response=httpx.Response(page["status"]))
        raise httpx.ConnectError(page.get("error", "saved error"))

    def chat(self, module: str):
        def ask(system: str, user: str, schema: dict, **kw):
            for i in self.unused:
                row = self.case.model[i]
                if row["module"] == module and system.startswith(row["system"]):
                    self.unused.remove(i)
                    return row["answer"]
            self.misses.append(f"model {module}: {system[:SYSTEM_KEY]!r}")
            raise AssertionError(f"model answer not in the saved case: {system[:SYSTEM_KEY]!r}")
        return ask


class Recorder:
    """Passes calls to the real web and model, saving every page and answer in the case format."""
    def __init__(self, case: Case, web, models: dict):
        self.case, self.web, self.models = case, web, models

    def fetch(self, url: str, client=None):
        try:
            final, html = self.web(url)
        except httpx.HTTPStatusError as e:
            self.case.pages.setdefault(url, {"status": e.response.status_code})
            raise
        except Exception as e:
            self.case.pages.setdefault(url, {"error": type(e).__name__})
            raise
        if url not in self.case.pages:
            name = f"page{len(self.case.files) + 1}.html"
            self.case.pages[url] = {"final": final, "file": name}
            self.case.files[name] = html
        return final, html

    def chat(self, module: str):
        def ask(system: str, user: str, schema: dict, **kw):
            answer = self.models[module](system, user, schema, **kw)
            self.case.model.append({"module": module, "system": system[:SYSTEM_KEY], "answer": answer})
            return answer
        return ask


@contextmanager
def stubbed(fetch, chat):
    """Swap the web and the model for the given functions, and keep the browser and stage updates out."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(pipeline, "fetch_text", fetch))
        stack.enter_context(patch.object(pricing, "fetch_text", fetch))
        for name, module in MODELS.items():
            stack.enter_context(patch.object(module, "chat_json", chat(name)))
        stack.enter_context(patch.object(browser, "available", lambda: False))
        stack.enter_context(patch.object(jobs, "set_stage", lambda *a, **k: None))
        yield


def replay(case: Case) -> tuple[list[dict], Tape]:
    tape = Tape(case)
    with stubbed(tape.fetch, tape.chat):
        return prepare_link(case.kind, case.url, case.caption, case.now), tape


def record(url: str, folder: Path, web, models: dict, now: datetime | None = None) -> Case:
    """Run an event page link through read and prepare, saving what it fetched and what the model said."""
    case = Case(kind="event_page", url=url, caption=None, now=now or datetime.now(timezone.utc))
    rec = Recorder(case, web, models)
    with stubbed(rec.fetch, rec.chat):
        case.expected = prepare_link(case.kind, url, None, case.now)
    save_case(case, folder)
    return case


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "record":
        from app.llm.ollama import chat_json
        from app.net import fetch_text
        case = record(argv[1], Path(argv[2]), fetch_text, {name: chat_json for name in MODELS})
        print(f"saved {len(case.pages)} pages and {len(case.model)} model answers to {argv[2]}")
        return 0
    if len(argv) == 2 and argv[0] == "show":
        got, tape = replay(load_case(Path(argv[1])))
        print(json.dumps(got, indent=2, ensure_ascii=False))
        for miss in tape.misses:
            print("not in the case:", miss, file=sys.stderr)
        return 1 if tape.misses else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
