# Instalator Pytajnika dla Windows (tryb lekki: STT i TTS na CPU, LLM z OpenRouter). Uruchamiany przez instaluj.bat.
#   1. uv (menedżer Pythona) - jeśli go nie ma, instalacja oficjalnym skryptem astral.sh
#   2. Python 3.11 i środowiska .venv-lekki, .venv-bot (paczki z wymagania\*.txt)
#   3. .env: klucz OpenRouter i głos
#   4. pobranie modeli (ok. 1,5 GB: Canary-1b-v2 int8 + wybrany głos)
#   5. skrót "Pytajnik" na pulpicie
# Ponowne uruchomienie jest bezpieczne: istniejące środowiska i .env zostają, można zmienić klucz i głos.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

$Glosy = @(
    @{ Nazwa = "supertonic-F1"; Opis = "Supertonic 3, kobiecy (najbardziej naturalny)" },
    @{ Nazwa = "supertonic-M1"; Opis = "Supertonic 3, męski" },
    @{ Nazwa = "matcha-female"; Opis = "Matcha-TTS-PL, kobiecy (najszybszy, mniej naturalny)" },
    @{ Nazwa = "matcha-male"; Opis = "Matcha-TTS-PL, męski" }
)

function Krok($tekst) { Write-Host ""; Write-Host "== $tekst" -ForegroundColor Cyan }

function Ustaw-Env($plik, $klucz, $wartosc) {
    # Podmienia KLUCZ=... w .env (także zakomentowane "# KLUCZ="), a jeśli go nie ma, dopisuje na końcu.
    $linie = @()
    if (Test-Path $plik) { $linie = @(Get-Content $plik -Encoding UTF8) }
    $wzor = "^\s*#?\s*$([regex]::Escape($klucz))="
    $jest = $false
    $nowe = foreach ($l in $linie) {
        if (-not $jest -and $l -match $wzor) { $jest = $true; "$klucz=$wartosc" } else { $l }
    }
    if (-not $jest) { $nowe = @($nowe) + "$klucz=$wartosc" }
    [System.IO.File]::WriteAllLines((Join-Path $Root $plik), [string[]]$nowe, (New-Object System.Text.UTF8Encoding $false))
}

function Czytaj-Env($plik, $klucz) {
    if (-not (Test-Path $plik)) { return "" }
    $m = Get-Content $plik -Encoding UTF8 | Where-Object { $_ -match "^\s*$([regex]::Escape($klucz))=(.*)$" } | Select-Object -Last 1
    if ($m -and $m -match "=(.*)$") { return $Matches[1].Trim() }
    return ""
}

try {
    Write-Host "Instalator Pytajnika (tryb lekki, bez GPU)" -ForegroundColor Green

    Krok "1/5 uv"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Instaluję uv (https://docs.astral.sh/uv/) ..."
        powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Nie udało się zainstalować uv." }
    }
    uv --version

    Krok "2/5 Python 3.11 i środowiska"
    foreach ($s in @(@{ Dir = ".venv-lekki"; Req = "wymagania\lekki.txt" }, @{ Dir = ".venv-bot"; Req = "wymagania\bot.txt" })) {
        if (Test-Path "$($s.Dir)\Scripts\python.exe") {
            Write-Host "$($s.Dir) już istnieje, aktualizuję paczki"
        } else {
            uv venv $s.Dir --python 3.11
            if ($LASTEXITCODE -ne 0) { throw "uv venv $($s.Dir) nie powiodło się" }
        }
        $env:VIRTUAL_ENV = Join-Path $Root $s.Dir
        uv pip install -r $s.Req
        if ($LASTEXITCODE -ne 0) { throw "Instalacja paczek do $($s.Dir) nie powiodła się" }
    }
    Remove-Item Env:VIRTUAL_ENV

    Krok "3/5 Ustawienia (.env)"
    if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
    Ustaw-Env ".env" "PYTAJNIK_SPRZET" "lekki"
    $klucz = Czytaj-Env ".env" "OPENROUTER_API_KEY"
    if ($klucz) {
        $nowy = Read-Host "Klucz OpenRouter jest już w .env. Enter = zostaw, albo wklej nowy"
    } else {
        Write-Host "Klucz założysz na https://openrouter.ai/keys"
        do { $nowy = Read-Host "Wklej klucz OpenRouter (sk-or-...)" } while (-not $nowy.Trim())
    }
    if ($nowy.Trim()) { Ustaw-Env ".env" "OPENROUTER_API_KEY" $nowy.Trim() }

    $obecny = Czytaj-Env ".env" "PYTAJNIK_GLOS_LEKKI"
    Write-Host "Głos Pytajnika:"
    for ($i = 0; $i -lt $Glosy.Count; $i++) {
        $znak = if ($Glosy[$i].Nazwa -eq $obecny) { "*" } else { " " }
        Write-Host (" {0}{1}. {2,-15} {3}" -f $znak, ($i + 1), $Glosy[$i].Nazwa, $Glosy[$i].Opis)
    }
    $wybor = Read-Host "Numer głosu (Enter = 1)"
    if (-not $wybor) { $wybor = "1" }
    $n = 0
    if (-not [int]::TryParse($wybor, [ref]$n) -or $n -lt 1 -or $n -gt $Glosy.Count) { $n = 1 }
    $glos = $Glosy[$n - 1].Nazwa
    Ustaw-Env ".env" "PYTAJNIK_GLOS_LEKKI" $glos
    Write-Host "Wybrany głos: $glos (zmienisz go w .env albo uruchamiając instalator ponownie)"

    Krok "4/5 Pobieranie modeli (ok. 1,5 GB, tylko za pierwszym razem)"
    & .venv-lekki\Scripts\python.exe stt_lekki\server.py --tylko-pobierz
    if ($LASTEXITCODE -ne 0) { throw "Pobranie modelu STT nie powiodło się" }
    & .venv-lekki\Scripts\python.exe tts_lekki\server.py --tylko-pobierz --voice $glos
    if ($LASTEXITCODE -ne 0) { throw "Pobranie głosu nie powiodło się" }

    Krok "5/5 Skrót na pulpicie"
    $pulpit = [Environment]::GetFolderPath("Desktop")
    $skrot = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $pulpit "Pytajnik.lnk"))
    $skrot.TargetPath = Join-Path $Root "uruchom.bat"
    $skrot.WorkingDirectory = $Root
    $skrot.Description = "Pytajnik - głosowy egzaminator"
    $skrot.Save()
    Write-Host "Utworzono: $pulpit\Pytajnik.lnk"

    Write-Host ""
    Write-Host "Gotowe. Uruchom Pytajnika skrótem na pulpicie albo plikiem uruchom.bat." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Błąd: $_" -ForegroundColor Red
    exit 1
}
