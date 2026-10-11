# Waiting on Zaher (updated 2026-10-11)

Done since the last list: Phases 4 + 5 are deployed (`acc5cca` on the Zephyrus, worker on the GPU with ffmpeg, yt-dlp and faster-whisper), the Ticketmaster key is set (dry run: ~760 events in the next 21 days, 4 calls), the Homarr tile is on both boards, and **Phase 6 is live**: https://dates.zkocr.com through Caddy + Cloudflare + Authentik (group `dates`: Zaher and Kathy).

1. **Deploy and recheck the map pins fix (`3bb9627`).** The first view was only handed to the list and the data fetch on the map's `load` event, which never fires if any style resource fails. It now also fires on `style.load`. Verified in the offline mock only; confirm on https://dates.zkocr.com after `scripts/deploy.sh`.
2. **Service worker does not register** in the Claude browser pane ("unknown error occurred when fetching the script", although `/service-worker.js` returns 200). Check in real Chrome on the phone before relying on Add to Home Screen.
3. **Try the video slow path.** Nothing has gone through the new code yet: all 6 ingests ran before the deploy, no media is archived, and Whisper has never run. Add one TikTok with no captions (Whisper downloads `large-v3-turbo` into `/srv/dateplanner/models` on first use; watch `docker compose logs -f worker` in `~/dateplanner/src/deploy`).
4. **"Save to Dates" Shortcut on the phones:** `docs/SHORTCUT.md` (the endpoint and key now work through https://dates.zkocr.com).
5. **Agent branches are merged (2026-10-11).** Phase 7 adapters (RA, Luma, Eventbrite web) and the Phase 8 planner core (OSRM client, picker, hours) are on main; their worktrees/branches can be deleted. Still missing: iCal, venue watch, SearXNG and Overpass adapters, scheduler, inbox, interests/scoring, plan CRUD, ICS feed, Plan page.
6. **After any `.env` change**, recreate every app container, including the dev copies (they only start under the `dev` profile):
   `ssh zephyrus "cd ~/dateplanner/src/deploy && docker compose --profile dev up -d"`
