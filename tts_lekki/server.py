#!/usr/bin/env python3
"""Usługa TTS trybu lekkiego (CPU, bez torcha): Supertonic 3 albo Matcha-TTS-PL-Edge-v2, API jak tts_voxcpm2/server.py.

  .venv-lekki/bin/python tts_lekki/server.py --port 8002 --voice supertonic-F1

Głosy (--voice, w .env PYTAJNIK_GLOS_LEKKI):
  supertonic-F1 … F5, supertonic-M1 … M5   Supertone/supertonic-3, ok. 99M, 44,1 kHz, gotowe głosy (OpenRAIL-M)
  matcha-female, matcha-male               machinekind/Matcha-TTS-PL-Edge-v2, ok. 21M, 22,05 kHz, fp32, 4 kroki
                                           (CC-BY-SA-4.0; fonetyzacja espeak-ng, GPL-3.0)
Pomiar na 4 rdzeniach i7-11700K (6 pytań quizu): Supertonic RTF ok. 0,17, Matcha ok. 0,075; oba czytają
poprawnie skróty typu VAT i KSeF. Matcha brzmi mniej naturalnie, Supertonic jest bliżej VoxCPM2.

POST /v1/audio/speech  JSON {"input": "...", "voice": "...", "response_format": "pcm"|"wav"}
  pcm -> strumień PCM s16le mono 48 kHz (jak VoxCPM2, więc bot się nie zmienia; nagłówek X-Sample-Rate)
  wav -> cały plik WAV
GET  /health, GET /v1/voices

Oba modele syntezują całe zdanie naraz (zdanie to ułamek sekundy); bot i tak wysyła tekst zdaniami.
Nazwy głosów OpenAI (alloy, nova, ...; wysyła je klient Pipecat) dostają --voice. Jedna synteza naraz.
"""
import argparse
import asyncio
import io
import os
import sys

import numpy as np
import soundfile as sf
import soxr
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

OUT_SR = 48000
SUPERTONIC = [f"supertonic-{g}{i}" for g in "FM" for i in range(1, 6)]
MATCHA = {"matcha-female": "female_voxcpm_2", "matcha-male": "male_voxcpm_2"}
MATCHA_REPO = "machinekind/Matcha-TTS-PL-Edge-v2"
MATCHA_REVISION = "8ac4956ca61f91732e99965a8645215f0a8bd383"
OPENAI_VOICES = {"alloy", "ash", "ballad", "cedar", "coral", "echo", "fable", "marin", "nova", "onyx", "sage",
                 "shimmer", "verse"}


class SpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    response_format: str = "pcm"
    model: str | None = None


class Supertonic:
    def __init__(self, voice, threads):
        from supertonic import TTS
        self.tts = TTS(auto_download=True, intra_op_num_threads=threads)
        self.style = self.tts.get_voice_style(voice_name=voice.split("-", 1)[1])
        self.sr = self.tts.sample_rate

    def __call__(self, text):
        wav, _ = self.tts.synthesize(text, voice_style=self.style, lang="pl")
        return np.asarray(wav, dtype=np.float32).squeeze()


class Matcha:
    def __init__(self, voice, threads):
        from huggingface_hub import snapshot_download
        name = MATCHA[voice]
        root = snapshot_download(MATCHA_REPO, revision=MATCHA_REVISION, allow_patterns=[
            "tts.py", "frontend/*", f"{name}/voices.json", f"{name}/encoder_sdp.onnx", f"{name}/decoder_t4.onnx",
            f"{name}/vocoder.onnx"])
        # Frontend (frontend/text.py) tworzy backend espeak-ng przy imporcie; systemowy espeak-ng bywa za stary
        # albo go nie ma, więc bierzemy bibliotekę z espeakng-loader.
        import espeakng_loader
        os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", espeakng_loader.get_library_path())
        os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())
        sys.path[:0] = [root, os.path.join(root, "frontend")]
        from tts import SR, EdgeTTS
        self.tts = EdgeTTS(voice=name, precision="fp32", steps=4, threads=threads, root=root)
        self.tts.warmup()
        self.sr = SR

    def __call__(self, text):
        return np.concatenate(list(self.tts.stream(text, stream=False)))


def to_s16le(chunk):
    return (np.clip(chunk, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def build_app(voice, threads):
    backend = (Supertonic if voice in SUPERTONIC else Matcha)(voice, threads)
    lock = asyncio.Lock()
    app = FastAPI(title="tts-lekki")

    def synthesize(text):
        return soxr.resample(backend(text), backend.sr, OUT_SR).astype(np.float32)

    synthesize("Rozgrzewka.")

    @app.get("/health")
    def health():
        return {"status": "ok", "voice": voice, "device": "cpu", "sample_rate": OUT_SR, "model_sample_rate": backend.sr}

    @app.get("/v1/voices")
    def list_voices():
        return {"voices": [voice]}

    @app.post("/v1/audio/speech")
    async def speech(req: SpeechRequest):
        if not req.input.strip():
            raise HTTPException(400, "Pusty tekst")
        if req.voice not in (None, "", voice) and req.voice not in OPENAI_VOICES:
            raise HTTPException(404, f"Nie ma głosu {req.voice!r}; serwer ma {voice!r} (zmień PYTAJNIK_GLOS_LEKKI)")
        if req.response_format not in ("pcm", "wav"):
            raise HTTPException(400, "response_format musi być pcm albo wav")
        async with lock:
            audio = await asyncio.to_thread(synthesize, req.input)
        headers = {"X-Sample-Rate": str(OUT_SR)}
        if req.response_format == "pcm":
            return StreamingResponse(iter([to_s16le(audio)]), media_type="audio/pcm", headers=headers)
        buf = io.BytesIO()
        sf.write(buf, audio, OUT_SR, format="WAV", subtype="PCM_16")
        return Response(buf.getvalue(), media_type="audio/wav", headers=headers)

    return app


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default="supertonic-F1", choices=SUPERTONIC + list(MATCHA))
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--tylko-pobierz", action="store_true", help="pobierz i załaduj model, potem wyjdź (instalator)")
    ap.add_argument("--port", type=int, default=8002)
    a = ap.parse_args()
    app = build_app(a.voice, a.threads)
    if not a.tylko_pobierz:
        uvicorn.run(app, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
