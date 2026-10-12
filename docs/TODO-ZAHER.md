# Waiting on Zaher (updated 2026-10-11)

Legend: [x] done, [~] done but needs your check, [ ] pending.

## Done
- [x] Phases 4 + 5 deployed (map UI, video slow path; worker on the GPU with ffmpeg, yt-dlp, faster-whisper).
- [x] Ticketmaster key set (dry run: ~760 events in the next 21 days, 4 calls).
- [x] Homarr tile on both boards.
- [x] Phase 6 live: https://dates.zkocr.com through Caddy + Cloudflare + Authentik (group `dates`: Zaher and Kathy).
- [x] Agent branches merged into main: RA, Luma, Eventbrite web adapters and the planner core (OSRM client, picker). Their worktrees and branches in `.claude/worktrees/` can be deleted.
- [x] One opening-hours module (`app/hours.py`) for the open-now filter and the picker.
- [x] `scripts/deploy.bat` one-click deploy.
- [x] Deployed `f959226` to the Zephyrus (REVISION confirmed, `/healthz` ok): includes the map pins fix and the merged adapters/planner.

## Needs your check
- [~] **Map pins fix (`3bb9627`, deployed).** Pins and list showed in the offline mock. Open https://dates.zkocr.com and confirm the 20 places and 1 event appear on the map and in the list. If still empty, the cause is elsewhere (check the browser console).

## Pending
- [ ] **Service worker does not register** in the Claude browser pane ("unknown error occurred when fetching the script", although `/service-worker.js` returns 200). Check in real Chrome on the phone before relying on Add to Home Screen.
- [ ] **Try the video slow path.** Whisper has never run (`/srv/dateplanner/models` does not exist yet, no media archived). Add one TikTok with no captions; `large-v3-turbo` downloads on first use. Watch `docker compose logs -f worker` in `~/dateplanner/src/deploy`.
- [ ] **"Save to Dates" Shortcut on the phones:** `docs/SHORTCUT.md` (endpoint and key work through https://dates.zkocr.com).
- [ ] **Still to build (Claude):** iCal, venue watch, SearXNG and Overpass adapters; scheduler and Suggested inbox; interests and scoring; plan CRUD, ICS feed and Plan page; Phase 9 lifecycle and ops.
- [ ] **After any `.env` change**, recreate every app container, including the dev copies:
  `ssh zephyrus "cd ~/dateplanner/src/deploy && docker compose --profile dev up -d"`
