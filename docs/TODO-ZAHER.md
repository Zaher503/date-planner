# Waiting on Zaher (updated 2026-10-11)

Done since the last list: Phases 4 + 5 are deployed (`acc5cca` on the Zephyrus, worker on the GPU with ffmpeg, yt-dlp and faster-whisper), the Ticketmaster key is set (dry run: ~760 events in the next 21 days, 4 calls), the Homarr tile is on both boards, and **Phase 6 is live**: https://dates.zkocr.com through Caddy + Cloudflare + Authentik (group `dates`: Zaher and Kathy).

1. **Map shows no pins (confirmed on the real server, 2026-10-11).** Signed in at dates.zkocr.com, `/api/map?bbox=...` returns the pins (20 places, 1 event) but neither the map nor the list shows any ("Nothing matches in this part of the map"). On one reload the base map did not draw either. Same symptom as the offline mock, so it is not caused by missing tiles or sprites. Look at `frontend/src/lib/map/` (style load vs adding the pin layer) and how the list reads the map's features.
2. **Service worker does not register** in the Claude browser pane ("unknown error occurred when fetching the script", although `/service-worker.js` returns 200). Check in real Chrome on the phone before relying on Add to Home Screen.
3. **Try the video slow path.** Nothing has gone through the new code yet: all 6 ingests ran before the deploy, no media is archived, and Whisper has never run. Add one TikTok with no captions (Whisper downloads `large-v3-turbo` into `/srv/dateplanner/models` on first use; watch `docker compose logs -f worker` in `~/dateplanner/src/deploy`).
4. **"Save to Dates" Shortcut on the phones:** `docs/SHORTCUT.md` (the endpoint and key now work through https://dates.zkocr.com).
5. **Unmerged agent branches (3 commits each, both stopped partway):**
   - `worktree-agent-acbe7cae544aaddc2`: discovery adapters (RA, Luma, Eventbrite, iCal).
   - `worktree-agent-a110dca7936cb47f7`: planner + ICS calendar backend. Caddy already passes `/cal/*` through without Authentik for its feed.
   Review with `git log main..<branch>`, then merge or finish them.
6. **After any `.env` change**, recreate every app container, including the dev copies (they only start under the `dev` profile):
   `ssh zephyrus "cd ~/dateplanner/src/deploy && docker compose --profile dev up -d"`
