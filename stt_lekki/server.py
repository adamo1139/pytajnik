#!/usr/bin/env python3
"""Usługa STT trybu lekkiego: Canary-1b-v2 w int8 (ONNX, onnx-asr) na CPU, API jak stt_canary/server.py.

  .venv-lekki/bin/python stt_lekki/server.py --port 8001 --threads 4

POST /v1/audio/transcriptions  (multipart: file=<audio>, language=pl, response_format=json|text)
  -> {"text": "..."}  (+ "duration" i "processing_s")
GET  /health

Ten sam model co na GPU, bez torcha: eksport istupakov/canary-1b-v2-onnx (int8 ok. 1 GB). Na 4 rdzeniach
i7-11700K wypowiedź 3–8 s przepisuje się w 0,6–1,5 s (RTF ok. 0,2), z jakością jak w pełnej precyzji.
Więcej wątków niewiele daje. Audio w dowolnym formacie czytanym przez soundfile, uśredniane do mono
i przepróbkowane do 16 kHz. Jedna transkrypcja naraz.
"""
import argparse
import asyncio
import io
import time

import numpy as np
import onnx_asr
import onnxruntime as rt
import soundfile as sf
import soxr
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from huggingface_hub import snapshot_download

SR = 16000
REPO = "istupakov/canary-1b-v2-onnx"
REVISION = "5ebc1520cef7b6b318b3526ad17adbfe00bc1bfc"


def build_app(threads):
    path = snapshot_download(REPO, revision=REVISION, allow_patterns=["*.int8.onnx", "config.json", "vocab.txt"])
    so = rt.SessionOptions()
    so.intra_op_num_threads = threads
    model = onnx_asr.load_model("nemo-canary-1b-v2", path, quantization="int8", sess_options=so)
    lock = asyncio.Lock()
    app = FastAPI(title="stt-lekki")

    def transcribe(audio, language):
        return model.recognize(audio, sample_rate=SR, language=language, pnc=True).strip()

    transcribe(np.zeros(SR, dtype=np.float32), "pl")  # rozgrzewka

    @app.get("/health")
    def health():
        return {"status": "ok", "model": f"{REPO} (int8)", "device": "cpu", "threads": threads}

    @app.post("/v1/audio/transcriptions")
    async def transcriptions(file: UploadFile = File(...), language: str = Form("pl"),
                             response_format: str = Form("json"), model_name: str = Form("", alias="model")):
        try:
            audio, sr = sf.read(io.BytesIO(await file.read()), dtype="float32", always_2d=True)
        except Exception as e:
            raise HTTPException(400, f"Nie da się odczytać audio: {e}")
        audio = audio.mean(axis=1)
        if sr != SR:
            audio = soxr.resample(audio, sr, SR).astype(np.float32)
        if len(audio) < SR // 10:
            return {"text": "", "duration": len(audio) / SR, "processing_s": 0.0}
        async with lock:
            start = time.time()
            text = await asyncio.to_thread(transcribe, audio, language)
            elapsed = time.time() - start
        if response_format == "text":
            return PlainTextResponse(text)
        return {"text": text, "duration": round(len(audio) / SR, 3), "processing_s": round(elapsed, 3)}

    return app


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--tylko-pobierz", action="store_true", help="pobierz i załaduj model, potem wyjdź (instalator)")
    ap.add_argument("--port", type=int, default=8001)
    a = ap.parse_args()
    app = build_app(a.threads)
    if not a.tylko_pobierz:
        uvicorn.run(app, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
