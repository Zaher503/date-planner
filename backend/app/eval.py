"""Accuracy check against the golden set. Reads links and resolves places but writes nothing.

    python -m app.eval [path/to/golden.json]
"""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from app.db.session import SessionLocal
from app.ingest import pipeline, store
from app.ingest.urls import classify
from app.resolve.candidates import km
from app.resolve.resolver import resolve
from app.resolve.scorer import name_similarity

DEFAULT = Path(__file__).resolve().parent.parent / "tests" / "golden.json"


def hints_for(db, case: dict):
    job = SimpleNamespace(id=-1)  # stage updates touch no row
    if "text" in case:
        src = SimpleNamespace(kind="text", url=None, caption=case["text"], raw={}, title=None)
        return pipeline._from_text(db, job, src)
    src = SimpleNamespace(kind=classify(case["url"]), url=case["url"], caption=None, raw={}, title=None,
                          transcript=None)
    if src.kind == "tiktok":
        return pipeline._from_tiktok(db, job, src)
    if src.kind in ("gmaps", "applemaps"):
        hints = pipeline._from_maps(src)
        return hints
    return pipeline._from_page(db, job, src)


def main(path: Path) -> None:
    golden = json.loads(path.read_text(encoding="utf-8"))
    tol_km = golden["tolerance_m"] / 1000
    found_total = expect_total = auto_ok = auto_wrong = 0
    with SessionLocal() as db:
        db.commit = db.flush  # never persist anything during an eval
        home = store.home_point(db)
        for case in golden["cases"]:
            label = case.get("url") or f"text: {case['text'][:40]}"
            t0 = time.time()
            try:
                hints = [pipeline.tidy(h, pipeline.datetime.now(pipeline.timezone.utc)) for h in hints_for(db, case)]
            except Exception as e:
                print(f"FAIL {label}: {type(e).__name__}: {e}")
                expect_total += len(case["expect"])
                continue
            t_read = time.time() - t0
            pins = []
            for h in hints:
                r = resolve(db, h, home)
                if r.best:
                    pins.append((h, r))
            t_all = time.time() - t0
            print(f"\n{label}\n  read {t_read:.1f}s, total {t_all:.1f}s, {len(hints)} items, {len(pins)} pinned")
            for h, r in pins:
                tag = "review" if r.needs_review else "auto"
                print(f"    [{tag} {r.confidence:.2f} {r.method}] {h.name} -> {r.best.name} | {r.best.address_text}")
            for exp in case["expect"]:
                expect_total += 1
                match = None
                for h, r in pins:
                    if name_similarity(exp["name"], h.name) >= 0.6 or name_similarity(exp["name"], r.best.name) >= 0.6 \
                            or exp["name"].lower() in (h.name + " " + r.best.name).lower():
                        match = (h, r)
                        break
                if not match:
                    print(f"  MISSING {exp['name']}")
                    continue
                h, r = match
                d = km(exp["near"][0], exp["near"][1], r.best.lat, r.best.lon)
                ok = d <= tol_km
                found_total += ok
                if not r.needs_review:
                    auto_ok += ok
                    auto_wrong += not ok
                print(f"  {'OK ' if ok else 'BAD'} {exp['name']}: {d * 1000:.0f} m off{' (auto-accepted!)' if not ok and not r.needs_review else ''}")
    print(f"\nCorrect place: {found_total}/{expect_total} ({100 * found_total / max(1, expect_total):.0f}%)."
          f" Auto-accepted correct: {auto_ok}, auto-accepted WRONG: {auto_wrong}.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
