# Awaryjne zatrzymanie Pytajnika na Windows: zabija procesy zapisane przez uruchom.ps1 (z procesami potomnymi).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path "logi\pids.txt")) { Write-Host "Pytajnik nie działa (brak logi\pids.txt)."; exit 0 }
foreach ($l in Get-Content "logi\pids.txt") {
    $id, $nazwa = $l -split " ", 2
    & taskkill /PID $id /T /F 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "zatrzymano $nazwa ($id)" }
}
Remove-Item "logi\pids.txt" -ErrorAction SilentlyContinue
