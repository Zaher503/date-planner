# Waiting on Zaher (updated 2026-10-12)

Legend: [x] done, [~] done but needs your check, [ ] pending.

## Done
- [x] Phases 4 + 5 deployed (map UI, video slow path; worker on the GPU with ffmpeg, yt-dlp, faster-whisper).
- [x] Ticketmaster key set (dry run: ~760 events in the next 21 days, 4 calls).
- [x] Homarr tile on both boards.
- [x] Phase 6 live: https://dates.zkocr.com through Caddy + Cloudflare + Authentik (group `dates`: Zaher and Kathy).
- [x] Agent branches merged into main: RA, Luma, Eventbrite web adapters and the planner core (OSRM client, picker). Their worktrees and branches in `.claude/worktrees/` can be deleted.
- [x] One opening-hours module (`app/hours.py`) for the open-now filter and the picker.
- [x] Push-to-deploy: CI and CD on GitHub (`Zaher503/date-planner`), images on GHCR, a self-hosted runner on the Zephyrus deploys to `/opt/date-planner` (replaces `deploy.sh`; `scripts/deploy.bat` re-runs the deploy).
- [x] Shared AI hub (2026-10-12): the LLM and Whisper moved out of this stack into `Zaher503/ai-hub`, which queues GPU work for Dates, Foodbox and the Transcriber and reports the wait. Jobs show "waiting for the AI (n ahead, about s)". A fixed `OLLAMA_URL` bug (the old Recipe Box container name) is gone with it.
- [x] Database wiped for a fresh start (backup `/srv/dateplanner/backups/pre-wipe-20261012-1338.sql`).
- [x] Map pins fix checked on the live site; teardrop pins with a centered category icon, rainbow count pins for mixed clusters and per-category colors in Settings are built (not deployed until the next push).

## Needs your check
- [~] **New pins.** After the next deploy, add a link and check the teardrop pins, the rainbow count pin and Settings > Pin colors on https://dates.zkocr.com.

## Pending
- [ ] **Service worker does not register** in the Claude browser pane ("unknown error occurred when fetching the script", although `/service-worker.js` returns 200). Check in real Chrome on the phone before relying on Add to Home Screen.
- [ ] **Try the video slow path.** Whisper runs in the AI hub now (large-v3, already cached, nothing downloads). Add one TikTok with no captions and watch `docker compose logs -f worker` in `/opt/date-planner/deploy` and `curl -s localhost:11434/queue` on the Zephyrus.
- [ ] **"Save to Dates" Shortcut on the phones:** `docs/SHORTCUT.md` (endpoint and key work through https://dates.zkocr.com).
- [ ] **Still to build (Claude):** iCal, venue watch, SearXNG and Overpass adapters; scheduler and Suggested inbox; interests and scoring; plan CRUD, ICS feed and Plan page; Phase 9 lifecycle and ops.
- [ ] **After any `.env` change**, recreate every app container, including the dev copies:
  `ssh zephyrus "cd /opt/date-planner/deploy && docker compose --profile dev up -d --force-recreate api worker api-dev worker-dev"`
