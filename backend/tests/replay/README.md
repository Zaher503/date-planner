# Saved import cases

Each folder in `cases/` is one link the importer read once. `test_replay.py` runs it through
`pipeline.read_link` and `pipeline.prepare` with the web and the model replaced by what was saved, and compares
the prepared hints with `expected.json`. It fails when the pipeline asks for a page or a model answer the case does
not hold, or when a saved model answer is never used. Nothing here needs a network, a model or a database.

Use it for daily import fixes: save the page that went wrong, fix the code, keep the case so it cannot come back.

## Files in a case folder

- `case.json` is the link and the pages the web returned for it.
  - `kind`: `event_page` or `text` (the kinds that need no map or video tools).
  - `url`, `caption` (the text for a `text` case, else null).
  - `now`: the clock for the "event already happened" check, for example `2026-10-10T12:00:00+00:00`.
  - `pages`: one entry per address the pipeline fetches, keyed by the address asked for. An entry is
    `{"final": "<address after redirects>", "file": "page.html"}`, or `{"status": 404}` for a page that refused,
    or `{"error": "ConnectError"}` for a page that could not be reached.
- `pages/*.html` are the saved pages named by the `file` fields.
- `model.json` is a list of the model answers, in the order they were asked:
  `{"module": "extract", "system": "<start of the system prompt>", "answer": {...}}`. `module` is `extract`
  (read the page or text, and the category step) or `pricing` (read a ticket page). `system` only needs to be the
  first words of the prompt. `answer` is the JSON the model returned.
  A page with structured data (JSON-LD) asks the model once, for categories and tags:
  `{"module": "extract", "system": "For each numbered place or event", "answer": {"items": [{"index": 0, "category": "bar", "tags": ["rooftop"]}]}}`.
- `expected.json` is the list of prepared hints: every field of the hint that is set (empty values left out),
  dates as ISO text.

## Add a case by hand

1. Make `cases/<name>/pages/` and save the page there.
2. Write `case.json` and `model.json`. Ticket links the pipeline follows to find a price are fetched too. If you
   do not have those pages, list them as `{"error": "ConnectError"}`; the first run names every address it asked for.
3. Run `python -m app.replay show tests/replay/cases/<name>` from `backend/` to print what the case produces.
   It lists anything the case lacks on stderr.
4. Read the output, and when it is right save it as `expected.json`.

## Record a case from a live link

From `backend/`, with the model reachable:

    python -m app.replay record <url> tests/replay/cases/<name>

It reads the event page link the way an import does and saves every page fetched, every model answer and the
resulting hints. The browser is switched off while recording so the case can be replayed. Check the saved
`expected.json` before you keep it.
