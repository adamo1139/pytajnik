#!/usr/bin/env bash
set -euo pipefail
# Pytajnik: TTS i STT lokalnie, LLM z OpenRouter, bot Pipecat. PYTAJNIK_SPRZET w .env:
#   pelny (domyślnie) - VoxCPM2 + Canary na GPU (~8 GB VRAM)
#   lekki             - Canary int8 + Supertonic 3 / Matcha na CPU (laptop bez GPU); głos: PYTAJNIK_GLOS_LEKKI
# Każda usługa startuje dopiero, gdy poprzednia odpowiada na /health.
#   bash uruchom.sh [domyślny_plik_z_pytaniami.txt]     # potem http://localhost:7860 (wgrywanie pytań)
#   bash zatrzymaj.sh
# Klucz: OPENROUTER_API_KEY=... w pliku .env obok tego skryptu (poza gitem) albo w zmiennej środowiskowej.
# Bot słucha na całej sieci (BOT_HOST=0.0.0.0), więc działa z innych urządzeń w tej samej sieci;
# BOT_HOST=localhost ogranicza go do tego komputera. STT i TTS zostają na 127.0.0.1.
if [[ $# -ge 1 ]]; then
    [[ -f "$1" ]] || { echo "Brak pliku: $1" >&2; exit 1; }
    export PYTANIA="$(realpath "$1")"
fi
cd "$(dirname "$0")"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${OPENROUTER_API_KEY:-}" ]] || { echo "Ustaw OPENROUTER_API_KEY w .env (https://openrouter.ai/keys)" >&2; exit 1; }
mkdir -p logi
: > logi/pids

start() {  # nazwa, port (0 = bez /health), polecenie...
    local name=$1 port=$2; shift 2
    nohup "$@" > "logi/${name}.log" 2>&1 &
    local pid=$!
    echo "${pid} ${name}" >> logi/pids
    [[ "${port}" == 0 ]] && return
    for _ in $(seq 1 200); do
        curl -sf "http://127.0.0.1:${port}/health" > /dev/null && { echo "${name}: gotowe (port ${port})"; return; }
        kill -0 "${pid}" 2> /dev/null || { echo "${name}: proces padł, zobacz logi/${name}.log" >&2; exit 1; }
        sleep 3
    done
    echo "${name}: brak odpowiedzi na /health po 10 min" >&2; exit 1
}

if [[ "${PYTAJNIK_SPRZET:-pelny}" == lekki ]]; then
    W="${PYTAJNIK_WATKI:-4}"
    start tts 8002 .venv-lekki/bin/python tts_lekki/server.py --port 8002 --voice "${PYTAJNIK_GLOS_LEKKI:-supertonic-F1}" --threads "${W}"
    start stt 8001 .venv-lekki/bin/python stt_lekki/server.py --port 8001 --threads "${W}"
else
    start tts 8002 .venv-tts/bin/python tts_voxcpm2/server.py --port 8002 --voices glosy --default-voice poziomka
    start stt 8001 .venv-stt/bin/python stt_canary/server.py --port 8001
fi
start bot 0 .venv-bot/bin/python bot/bot.py -t webrtc --host "${BOT_HOST:-0.0.0.0}" --port "${BOT_PORT:-7860}"
for _ in $(seq 1 40); do
    curl -sf -o /dev/null "http://localhost:${BOT_PORT:-7860}/client/" && break
    sleep 1
done
echo "Pytajnik: http://localhost:${BOT_PORT:-7860}"
[[ "${BOT_HOST:-0.0.0.0}" == 0.0.0.0 ]] && echo "w sieci:   http://$(hostname -I | awk '{print $1}'):${BOT_PORT:-7860}"
if [[ "${PYTAJNIK_SPRZET:-pelny}" != lekki ]] && command -v nvidia-smi > /dev/null; then
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
fi
