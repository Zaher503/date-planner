# Sending date ideas

Endpoint: `POST https://dates.zkocr.com/api/add`
Header: `X-Dates-Key: <DATES_KEY from ~/dateplanner/.env on the Zephyrus>`
Body: JSON `{"url": "<link>"}` or `{"text": "<anything>"}`. A whole shared message works too; the first link in it is used. Optional `"user": "zaher"` or `"katherine"` marks who sent it (the name must have opened the app once).
Replies: `{"status": "queued"}`, `{"status": "exists"}` (already saved) or `{"status": "stub"}` (Instagram, saved for review). 401 = wrong key, 413 = body over 16 KB, 429 = more than 30 links a minute.
Browse: https://dates.zkocr.com (Authentik login, group `dates`).

## iPhone "Save to Dates" Shortcut (Share Sheet)

1. Shortcuts app > + > name it "Save to Dates".
2. Tap (i) > turn on "Show in Share Sheet" > Share Sheet Types: URLs, Text and Safari web pages.
3. Add "Get Contents of URL":
   - URL: `https://dates.zkocr.com/api/add`
   - Show More > Method: POST
   - Headers > Add new header: `X-Dates-Key` = the key
   - Request Body: JSON > Add new field > Text: key `text`, value "Shortcut Input"
   - Add another Text field: key `user`, value `zaher` (Katherine's copy uses `katherine`)
4. Add "Get Dictionary Value" for key `status` from "Contents of URL".
5. Add "If" Dictionary Value is `exists` > "Show Notification" "Already saved"; Otherwise > "Show Notification" "Sent to Dates".

Use: in TikTok, Safari, Google Maps or Apple Maps tap Share > Save to Dates. Sending `text` (not `url`) is deliberate: the server finds the link inside whatever was shared, and plain notes ("Rooftop jazz at Perch on Saturday") work too.

## Android

Open https://dates.zkocr.com in Chrome and choose Add to Home Screen. The installed app then appears in the share sheet and opens the Add box with the shared link filled in.

## Windows

```powershell
.\scripts\add-date.ps1 https://www.tiktok.com/@someone/video/123
.\scripts\add-date.ps1 Rooftop jazz at Perch, Saturday 8pm
.\scripts\add-date.ps1            # uses the clipboard
```

Put the key in `scripts/.secret` first (ignored by git). `DATES_URL` overrides the server (for example `http://192.168.0.169:8820` on the LAN).

## Rotating the key

Edit `DATES_KEY` in `~/dateplanner/.env` on the Zephyrus, run `scripts/deploy.sh api`, then update the Shortcut(s) and `scripts/.secret`.
