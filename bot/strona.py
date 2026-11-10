"""Strona startowa: wgrywanie własnych pytań i wybór zestawu, osobno dla każdego urządzenia.

Trasy dokładane do aplikacji FastAPI runnera Pipecat (pipecat.runner.run.app) przed main():
  GET  /                 strona (strona.html); prebuilt UI rozmowy zostaje pod /client
  GET  /api/zestawy      zapisane zestawy i ten wybrany na tym urządzeniu
  POST /api/pytania      {"tekst", "nazwa"} -> model wyciąga pytania, zestaw zostaje wybrany
  POST /api/zestaw/{id}  wybór zapisanego zestawu

Wybrany zestaw jest w ciasteczku "zestaw". Prebuilt UI nie pozwala dołożyć niczego do żądania
/api/offer, ale wysyła ciasteczka, a runner uruchamia bota w zadaniu tła tego samego żądania.
Dlatego middleware przepisuje ciasteczko do zmiennej kontekstowej, którą bot czyta na starcie.
"""
import asyncio
import contextvars
import os
from http.cookies import SimpleCookie

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from openai import OpenAI
from pipecat.runner.run import app
from pydantic import BaseModel

import pytania

ZESTAW = contextvars.ContextVar("zestaw", default=None)
CIASTECZKO = 60 * 60 * 24 * 365


class ZestawZCiasteczka:
    """ASGI middleware: ciasteczko "zestaw" -> ZESTAW na czas całego żądania (z zadaniami tła)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            naglowki = dict(scope.get("headers") or [])
            ciastka = SimpleCookie(naglowki.get(b"cookie", b"").decode("latin-1"))
            if "zestaw" in ciastka:
                ZESTAW.set(ciastka["zestaw"].value)
        await self.app(scope, receive, send)


def zainstaluj(client: OpenAI, model: str, domyslny: str | None):
    """Dokłada trasy i middleware; domyslny to id zestawu z PYTANIA dla urządzeń bez wyboru."""
    app.add_middleware(ZestawZCiasteczka)

    def wybrany(zid: str | None) -> str | None:
        try:
            if zid and os.path.exists(pytania.sciezka_zestawu(zid)):
                return zid
        except ValueError:
            pass
        return domyslny

    def odpowiedz(zid: str) -> JSONResponse:
        z = pytania.zestaw(zid)
        r = JSONResponse({"id": zid, "nazwa": z["nazwa"], "pytania": z["pytania"]})
        r.set_cookie("zestaw", zid, max_age=CIASTECZKO, samesite="lax")
        return r

    @app.get("/", include_in_schema=False)
    async def strona():
        return FileResponse(os.path.join(os.path.dirname(__file__), "strona.html"))

    @app.get("/api/zestawy")
    async def lista_zestawow():
        zid = wybrany(ZESTAW.get())
        z = pytania.zestaw(zid) if zid else None
        return {"wybrany": zid, "pytania": z["pytania"] if z else [], "zestawy": pytania.zestawy()}

    class Tekst(BaseModel):
        tekst: str
        nazwa: str = ""

    @app.post("/api/pytania")
    async def wgraj(t: Tekst):
        try:
            # Wywołanie modelu trwa kilkadziesiąt sekund; w wątku, żeby nie blokować trwających rozmów.
            zid = await asyncio.to_thread(pytania.wyciagnij, t.tekst, client, model, t.nazwa.strip())
        except ValueError as e:
            raise HTTPException(400, str(e))
        return odpowiedz(zid)

    @app.post("/api/zestaw/{zid}")
    async def wybierz(zid: str):
        if wybrany(zid) != zid:
            raise HTTPException(404, "nie ma takiego zestawu")
        return odpowiedz(zid)

    return lambda: wybrany(ZESTAW.get())
