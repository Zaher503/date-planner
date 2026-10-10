# Send a date idea (TikTok, maps link, event page or plain text) to the Date Planner.
# Usage:  .\add-date.ps1 <link or text>     With no argument it uses the clipboard.
# The key lives in .secret next to this script (DATES_KEY from ~/dateplanner/.env).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Text)
$keyFile = Join-Path $PSScriptRoot ".secret"
if (-not (Test-Path $keyFile)) { Write-Host "Put the DATES_KEY in $keyFile first." -ForegroundColor Red; exit 1 }
$key = (Get-Content $keyFile -Raw).Trim()
$value = ($Text -join " ").Trim()
if (-not $value) { $value = (Get-Clipboard -Raw).Trim() }
if (-not $value) { Write-Host "Nothing to send: give a link or text, or copy one first." -ForegroundColor Red; exit 1 }
$base = if ($env:DATES_URL) { $env:DATES_URL } else { "https://dates.zkocr.com" }
$body = if ($value -match '^https?://\S+$') { @{ url = $value } } else { @{ text = $value } }
try {
  $r = Invoke-RestMethod -Method Post -Uri "$base/api/add" `
        -Headers @{ "X-Dates-Key" = $key } -ContentType "application/json" `
        -Body ($body | ConvertTo-Json) -TimeoutSec 20
  switch ($r.status) {
    "exists" { Write-Host "Already saved." -ForegroundColor Yellow }
    "stub"   { Write-Host "Saved for manual review (this kind of link cannot be read)." -ForegroundColor Yellow }
    default  { Write-Host "Sent. The pin appears in under a minute." -ForegroundColor Green }
  }
} catch { Write-Host "Failed: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
