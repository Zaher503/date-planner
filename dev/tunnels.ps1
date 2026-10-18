# SSH tunnels from the desktop to the Zephyrus services the dev stack needs (loopback only).
# 11435 because a local Ollama may own 11434.
# Container IPs on dates_default can change after a redeploy; this looks them up each time.
$ips = ssh zephyrus 'for c in dates-photon-1 dates-searxng-1; do docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}" $c; done'
$photon, $searx = ($ips -split "`n" | ForEach-Object { ($_ -split " ")[0].Trim() })
Write-Host "photon $photon, searxng $searx; Ctrl+C to close"
ssh -N -o ExitOnForwardFailure=yes `
  -L "127.0.0.1:11435:localhost:11434" `
  -L "127.0.0.1:2322:${photon}:2322" `
  -L "127.0.0.1:8080:${searx}:8080" zephyrus
