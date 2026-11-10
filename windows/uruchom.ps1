# Uruchamia Pytajnika na Windows (tryb lekki): STT -> TTS -> bot, potem otwiera przeglądarkę.
# Uruchamiany przez uruchom.bat; opcjonalnie domyślny plik z pytaniami:  uruchom.bat pytania\podatki.txt
# Enter w tym oknie zatrzymuje wszystko (awaryjnie: zatrzymaj.bat). Logi w logi\*.log.
param([string]$Pytania = "")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Blad($tekst) { Write-Host $tekst -ForegroundColor Red; Read-Host "Enter zamyka okno" | Out-Null; exit 1 }

# .env -> zmienne środowiskowe (te już ustawione mają pierwszeństwo, jak w bot/pytania.py)
if (-not (Test-Path ".env")) { Blad "Brak pliku .env - uruchom najpierw instaluj.bat" }
foreach ($l in Get-Content ".env" -Encoding UTF8) {
    if ($l -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$" -and $Matches[2].Trim()) {
        $k = $Matches[1]; $v = $Matches[2].Trim().Trim('"').Trim("'")
        if (-not [Environment]::GetEnvironmentVariable($k)) { [Environment]::SetEnvironmentVariable($k, $v) }
    }
}
if (-not $env:OPENROUTER_API_KEY) { Blad "Brak OPENROUTER_API_KEY w .env - uruchom instaluj.bat albo wpisz klucz do .env" }
if (-not (Test-Path ".venv-lekki\Scripts\python.exe") -or -not (Test-Path ".venv-bot\Scripts\python.exe")) {
    Blad "Brak środowisk .venv-lekki / .venv-bot - uruchom najpierw instaluj.bat"
}
if ($Pytania) {
    if (-not (Test-Path $Pytania)) { Blad "Brak pliku: $Pytania" }
    $env:PYTANIA = (Resolve-Path $Pytania).Path
}
$env:PYTHONUTF8 = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$glos = if ($env:PYTAJNIK_GLOS_LEKKI) { $env:PYTAJNIK_GLOS_LEKKI } else { "supertonic-F1" }
$watki = if ($env:PYTAJNIK_WATKI) { $env:PYTAJNIK_WATKI } else { "4" }
# Na Windows domyślnie tylko ten komputer: 0.0.0.0 wywołuje pytanie zapory, a mikrofon przez http i tak działa
# w przeglądarce tylko na localhost.
$hostBota = if ($env:BOT_HOST) { $env:BOT_HOST } else { "localhost" }
$port = if ($env:BOT_PORT) { $env:BOT_PORT } else { "7860" }

New-Item -ItemType Directory -Force logi | Out-Null
$procesy = @()

function Start-Usluga($nazwa, $port, [string[]]$argumenty, $python) {
    $p = Start-Process -FilePath (Join-Path $Root $python) -ArgumentList $argumenty -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "logi\$nazwa.log" -RedirectStandardError "logi\$nazwa.err.log"
    Add-Content "logi\pids.txt" "$($p.Id) $nazwa"
    $script:procesy += $p
    if (-not $port) { return }
    Write-Host -NoNewline "${nazwa}: ładowanie"
    for ($i = 0; $i -lt 200; $i++) {
        try {
            Invoke-WebRequest "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
            Write-Host " - gotowe (port $port)"; return
        } catch {}
        if ($p.HasExited) {
            Write-Host ""; Get-Content "logi\$nazwa.err.log" -Tail 15 -ErrorAction SilentlyContinue
            Zatrzymaj; Blad "${nazwa}: proces padł, zobacz logi\$nazwa.err.log"
        }
        Write-Host -NoNewline "."; Start-Sleep -Seconds 3
    }
    Zatrzymaj; Blad "${nazwa}: brak odpowiedzi po 10 minutach"
}

function Zatrzymaj {
    # W Windows PowerShell 5.1 stderr programu z 2>&1 przy "Stop" staje się wyjątkiem; tu błędy taskkill nie mają znaczenia.
    $ErrorActionPreference = "Continue"
    foreach ($p in $script:procesy) {
        if (-not $p.HasExited) { & taskkill /PID $p.Id /T /F 2>&1 | Out-Null }
    }
    Remove-Item "logi\pids.txt" -ErrorAction SilentlyContinue
}

Remove-Item "logi\pids.txt" -ErrorAction SilentlyContinue
Write-Host "Pytajnik (tryb lekki), głos: $glos" -ForegroundColor Green
Start-Usluga "stt" 8001 @("stt_lekki\server.py", "--port", "8001", "--threads", $watki) ".venv-lekki\Scripts\python.exe"
Start-Usluga "tts" 8002 @("tts_lekki\server.py", "--port", "8002", "--voice", $glos, "--threads", $watki) ".venv-lekki\Scripts\python.exe"
Start-Usluga "bot" $null @("bot\bot.py", "-t", "webrtc", "--host", $hostBota, "--port", $port) ".venv-bot\Scripts\python.exe"

$adres = "http://localhost:$port"
Write-Host -NoNewline "bot: start"
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest "$adres/client/" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch {}
    if ($procesy[-1].HasExited) {
        Write-Host ""; Get-Content "logi\bot.err.log" -Tail 15 -ErrorAction SilentlyContinue
        Zatrzymaj; Blad "bot: proces padł, zobacz logi\bot.err.log"
    }
    Write-Host -NoNewline "."; Start-Sleep -Seconds 1
}
Write-Host ""
Write-Host "Pytajnik działa: $adres" -ForegroundColor Green
Start-Process $adres
Read-Host "Enter zatrzymuje Pytajnika" | Out-Null
Zatrzymaj
Write-Host "Zatrzymano."
