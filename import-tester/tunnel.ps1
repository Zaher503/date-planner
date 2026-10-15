# Opens one SSH tunnel to the Zephyrus so this PC can reach the AI hub (Ollama) and the stack's
# browser, SearXNG and Photon containers (which have no published ports)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $here ".tunnel.pid"

function Test-Port($port) {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $port); $c.Close(); return $true } catch { return $false }
}

# Replace a tunnel left over from an earlier run
if (Test-Path $pidFile) {
    Stop-Process -Id ([int](Get-Content $pidFile)) -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (Test-Port 11434) { Write-Host "Port 11434 is already in use by something else, skipping tunnel"; exit 0 }

# container, port inside it, port on this PC
$services = @(
    @("dates-browser-1", 3000, 3000, "browser"),
    @("dates-searxng-1", 8080, 8080, "searxng"),
    @("dates-photon-1", 2322, 2322, "photon")
)

$remote = "for c in " + (($services | ForEach-Object { $_[0] }) -join " ") + "; do echo `$c `$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' `$c | cut -d' ' -f1); done"
$ips = @{}
try {
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote))
    $out = ssh -o BatchMode=yes -o ConnectTimeout=8 zephyrus "echo $b64 | base64 -d | bash"
    foreach ($line in $out) { $p = "$line".Trim() -split "\s+"; if ($p.Count -ge 2) { $ips[$p[0]] = $p[1] } }
} catch { }

$forwards = @("-L", "11434:127.0.0.1:11434")
$names = @("AI hub")
foreach ($s in $services) {
    $ip = $ips[$s[0]]
    if ($ip -match "^\d+\.\d+\.\d+\.\d+$") { $forwards += @("-L", "$($s[2]):${ip}:$($s[1])"); $names += $s[3] }
    else { Write-Host "$($s[3]) container not found, that feature will be off" }
}

$p = Start-Process ssh -ArgumentList (@("-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30") + $forwards + "zephyrus") -WindowStyle Hidden -PassThru
Set-Content $pidFile $p.Id
Start-Sleep -Seconds 3
if (Test-Port 11434) { Write-Host "Tunnel up: $($names -join ', ')" } else { Write-Host "Tunnel failed - check that 'ssh zephyrus' works" }
