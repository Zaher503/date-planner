# Waiting on Zaher (session 2, 2026-10-10)

1. **Deploy Phase 4 + 5.** The permission guard blocked `scripts/deploy.sh` (production deploy), so nothing new is live yet. Run it yourself: `scripts/deploy.sh`. The first build is large (faster-whisper + CUDA wheels). Map glyphs/sprites are already installed in `/srv/dateplanner/tiles/assets`.
2. **After deploying, check:** the map loads at http://192.168.0.172:8820 through the NAS, pins appear, and the worker starts with `runtime: nvidia` (`docker compose logs worker`). Then try one TikTok with no captions to exercise the slow path (Whisper downloads `large-v3-turbo` into `/srv/dateplanner/models` on first use).
3. **Open UI bug to look at:** in the offline mock (`npm --prefix frontend run dev:mock`), the map sometimes never fires `style.load`, so pins do not show. The mock has no tiles or sprites (404s). It may not happen on the real server, where those files exist. Check it after deploying; if it does happen, drop `sprite` from `frontend/src/lib/map/style.ts` or add pins on `load` as a fallback.
4. **Unfinished agent branches (not merged):**
   - `worktree-agent-acbe7cae544aaddc2`: discovery adapters (RA, Luma, Eventbrite, iCal). Stopped partway.
   - `worktree-agent-a110dca7936cb47f7`: planner + ICS calendar backend. Stopped partway.
   Review them with `git log main..<branch>`, then merge them or finish them.
5. **Phase 6 (needs you):** NAS Caddy block (`deploy/caddy-snippet.txt`), Cloudflare CNAME, Authentik app/group `dates` (add Katherine). Shortcut guide: `docs/SHORTCUT.md`.
6. Ticketmaster key, still pending.
