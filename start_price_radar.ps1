# price-radar launcher (generic): reads .env, starts uvicorn.
# NOTE: no CJK literals here on purpose - PS1 without BOM + CJK = mojibake.
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path "$root\logs")) { New-Item -ItemType Directory -Path "$root\logs" | Out-Null }

# Port from .env SERVER_PORT (default 8010; skip common ports like 8000/8080)
$port = 8010
if (Test-Path "$root\.env") {
    $m = Select-String -Path "$root\.env" -Pattern '^SERVER_PORT=(\d+)' | Select-Object -First 1
    if ($m) { $port = $m.Matches[0].Groups[1].Value }
}

Write-Output "[price-radar] starting on http://127.0.0.1:$port (AI key & all config read from .env)"
python -m uvicorn src.app:app --host 127.0.0.1 --port $port *>> "$root\logs\service.log"
