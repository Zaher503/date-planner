# Waiting on Zaher (updated 2026-10-11)

Done since the last list: Phases 4 + 5 are deployed (`acc5cca` on the Zephyrus, worker on the GPU with ffmpeg, yt-dlp and faster-whisper), the Ticketmaster key is set (dry run: ~760 events in the next 21 days, 4 calls), and the Homarr tile is on both boards.

1. **Try the deployed app.** Nothing has gone through the new code yet: all 6 ingests ran before the deploy, no media is archived, and Whisper has never run. Open the map through the NAS, check pins show, then add one TikTok with no captions to exercise the slow path (Whisper downloads `large-v3-turbo` into `/srv/dateplanner/models` on first use; watch `docker compose logs -f worker` in `~/dateplanner/src/deploy`).
2. **Map pins bug, check on the real server.** In the offline mock (`npm --prefix frontend run dev:mock`) the map sometimes never fires `style.load`, so pins do not show. The mock has no tiles or sprites (404s), so it may not happen on the server. If it does, drop `sprite` from `frontend/src/lib/map/style.ts` or add pins on `load` as a fallback.
3. **Phase 6 (needs you, not started on the NAS).** There is no `dates` block in the NAS Caddyfile and no public DNS record yet:
   - Caddy block from `deploy/caddy-snippet.txt` (back up the Caddyfile first).
   - Cloudflare CNAME `dates` -> `zkocr.com`, proxied.
   - Authentik proxy provider + application `dates`, group `dates` (you and Katherine).
   - Then the "Save to Dates" Shortcut: `docs/SHORTCUT.md`.
   The Homarr tile already points at `https://dates.zkocr.com` and starts working once this is done.
4. **Unmerged agent branches (3 commits each, both stopped partway):**
   - `worktree-agent-acbe7cae544aaddc2`: discovery adapters (RA, Luma, Eventbrite, iCal).
   - `worktree-agent-a110dca7936cb47f7`: planner + ICS calendar backend.
   Review with `git log main..<branch>`, then merge or finish them.
5. **After any `.env` change**, recreate every app container, including the dev copies (they only start under the `dev` profile):
   `ssh zephyrus "cd ~/dateplanner/src/deploy && docker compose --profile dev up -d"`
