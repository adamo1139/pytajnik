#!/usr/bin/env bash
set -euo pipefail
# Tworzy środowiska uv dla usług Pytajnika, z wersjami, na których wszystko było testowane
# (Linux x86_64, RTX 5080, sterownik NVIDIA 590.48, uv 0.7.19, Python 3.11).
#   bash setup_venvs.sh                 # tts stt bot
#   VENV_DIR=/inny/dysk bash setup_venvs.sh tts stt   # venvy na innym dysku, tu tylko dowiązania .venv-*
#     (cache uv też tam, w ${VENV_DIR}/.uv-cache, żeby venvy dzieliły pliki torcha przez hardlinki)
# Każda usługa ma osobne środowisko, bo ich zależności się wykluczają. LLM jest z OpenRouter.
cd "$(dirname "$0")"
PY="${PY:-3.11}"
CU128=https://download.pytorch.org/whl/cu128

if [[ -n "${VENV_DIR:-}" ]]; then
    mkdir -p "${VENV_DIR}"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-${VENV_DIR}/.uv-cache}"
fi

make_venv() {  # nazwa, argumenty uv pip install...
    local link=".venv-$1" dir="${VENV_DIR:-.}/.venv-$1"; shift
    [[ -e "${link}" ]] && { echo "${link} już istnieje, pomijam"; return; }
    echo "== ${dir}"
    uv venv "${dir}" --python "${PY}" -q
    VIRTUAL_ENV="${dir}" uv pip install -q "$@"
    [[ "${dir}" == "./${link}" ]] || ln -s "${dir}" "${link}"
}

tts() {  # VoxCPM2 (TTS) — torch 2.8 cu128
    make_venv tts "torch==2.8.0" "torchaudio==2.8.0" "torchcodec==0.7.0" "voxcpm==2.0.3" "transformers==5.20.2" \
        "fastapi==0.162.0" "uvicorn[standard]==0.54.0" "python-multipart==0.0.32" "httpx==0.28.1" "soundfile==0.14.0" \
        --extra-index-url "${CU128}" --index-strategy unsafe-best-match
}
stt() {  # Canary-1b-v2 przez transformers (bez NeMo) — torch 2.8 cu128
    make_venv stt "torch==2.8.0" "torchaudio==2.8.0" "transformers==5.20.2" "librosa==0.11.0" "soundfile==0.14.0" \
        "jiwer==4.0.0" "pyarrow==26.0.0" "fastapi==0.162.0" "uvicorn[standard]==0.54.0" "python-multipart==0.0.32" \
        "httpx==0.28.1" --extra-index-url "${CU128}" --index-strategy unsafe-best-match
}
bot() {  # Pipecat: WebRTC + prebuilt UI (runner), Silero VAD, klienci OpenAI
    make_venv bot "pipecat-ai[webrtc,runner,silero,openai]==1.14.0" "httpx==0.28.1"
}

command -v uv > /dev/null || { echo "Brak uv: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
for target in "${@:-tts stt bot}"; do
    for t in ${target}; do
        declare -F "${t}" > /dev/null || { echo "Nieznane środowisko: ${t} (tts stt bot)" >&2; exit 1; }
        "${t}"
    done
done
echo "Gotowe. Start: OPENROUTER_API_KEY=... bash uruchom.sh pytania/przyklad.txt"
