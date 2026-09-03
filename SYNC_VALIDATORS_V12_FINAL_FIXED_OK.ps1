$ErrorActionPreference = 'Stop'

Write-Host '=== HNK V12.2 VALIDATOR SYNC - CLEAN FIX ===' -ForegroundColor Cyan

# 1) Check containers
$ps = docker compose ps
$ps | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { throw 'docker compose ps failed' }

# 2) Health check all nodes
foreach ($node in @('node1','node2','node3')) {
    docker compose exec -T $node python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5); print('$node HEALTH OK')"
    if ($LASTEXITCODE -ne 0) { throw "$node health check failed" }
}

# 3) Read active validators from node1.
# Python source is base64 encoded so PowerShell quoting cannot corrupt SQL/Python strings.
$pyRead = @'
import json
from server import ledger
rows = ledger.db.execute(
    "SELECT v.address,v.power,v.active,v.jailed,k.public_key "
    "FROM validators v JOIN validator_keys k ON k.address=v.address "
    "WHERE v.active=1 AND v.jailed=0 ORDER BY v.address"
).fetchall()
print(json.dumps([list(r) for r in rows], separators=(',', ':')))
'@
$pyReadB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pyRead))
$raw = docker compose exec -T node1 python -c "import base64; exec(base64.b64decode('$pyReadB64').decode('utf-8'))"
if ($LASTEXITCODE -ne 0) { throw 'node1 validator read failed' }

$jsonLine = ($raw | Select-String -Pattern '^\[.*\]$' | Select-Object -Last 1).Line
if ([string]::IsNullOrWhiteSpace($jsonLine)) { throw 'node1 returned no validator JSON' }

$validators = $jsonLine | ConvertFrom-Json
if ($validators.Count -lt 1) { throw 'node1 has no active validators' }

Write-Host "NODE1 active validators: $($validators.Count)" -ForegroundColor Green
foreach ($v in $validators) {
    Write-Host ("  {0} power={1}" -f $v[0], $v[1])
}

# 4) Transport the ORIGINAL JSON as base64. Do not ConvertTo-Json it in PowerShell.
$jsonB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($jsonLine))

$pySync = @'
import os,base64,json
from server import ledger
rows = json.loads(base64.b64decode(os.environ['VJSONB64']).decode('utf-8'))
for r in rows:
    ledger.db.execute(
        "INSERT OR REPLACE INTO validators(address,power,active,jailed) VALUES(?,?,?,?)",
        (r[0], int(r[1]), int(r[2]), int(r[3]))
    )
    ledger.db.execute(
        "INSERT OR REPLACE INTO validator_keys(address,public_key) VALUES(?,?)",
        (r[0], r[4])
    )
ledger.db.commit()
print("SYNCED", len(rows), "validators")
'@
$pySyncB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pySync))

foreach ($node in @('node2','node3')) {
    Write-Host "SYNC -> $node" -ForegroundColor Yellow
    docker compose exec -T -e "VJSONB64=$jsonB64" $node python -c "import base64; exec(base64.b64decode('$pySyncB64').decode('utf-8'))"
    if ($LASTEXITCODE -ne 0) { throw "$node validator sync failed" }
}

# 5) Verify all nodes. Also avoid PowerShell/Python nested quote problems.
$pyVerify = @'
from server import ledger
print("VALIDATORS=", ledger.validator_set())
print("TOTAL_POWER=", ledger.total_power())
row = ledger.db.execute("SELECT MAX(height) FROM blocks").fetchone()
print("HEIGHT=", row[0] if row else None)
'@
$pyVerifyB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pyVerify))

Write-Host ''
Write-Host '=== VERIFY ===' -ForegroundColor Cyan
foreach ($node in @('node1','node2','node3')) {
    Write-Host "----- $node -----" -ForegroundColor Yellow
    docker compose exec -T $node python -c "import base64; exec(base64.b64decode('$pyVerifyB64').decode('utf-8'))"
    if ($LASTEXITCODE -ne 0) { throw "$node verification failed" }
}

Write-Host ''
Write-Host 'DONE: validator set synchronized and verified.' -ForegroundColor Green
