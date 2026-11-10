#!/usr/bin/env python3
"""Pytajnik — głosowy egzaminator (Pipecat): Silero VAD v6 -> Canary (STT) -> LLM z OpenRouter -> VoxCPM2 (TTS).

  PYTANIA=pytania/przyklad.txt .venv-bot/bin/python bot/bot.py -t webrtc --host 0.0.0.0
  # strona: http://localhost:7860 (wgrywanie pytań), rozmowa: http://localhost:7860/client

Pytania wgrywa się na stronie startowej (bot/strona.py) jako dowolny tekst, np. wklejony z PDF; model
wyciąga z niego pytania. Każde urządzenie ma własny wybrany zestaw (ciasteczko), a bez wyboru dostaje
zestaw z pliku PYTANIA. Przy każdym połączeniu bot losuje kolejność i zadaje pytania po jednym; po każdej
odpowiedzi ocenia ją i daje wskazówkę, na końcu podsumowuje.

Zmienne środowiskowe:
  PYTANIA              domyślny plik z pytaniami w dowolnym formacie, np. tekst z PDF (opcjonalny)
  OPENROUTER_API_KEY   klucz OpenRouter (wymagany; może być w .env w katalogu projektu)
  PYTAJNIK_MODEL       model na OpenRouter, domyślnie openai/gpt-6.1-sol
  PYTAJNIK_REASONING   reasoning effort (minimal/low/medium/high), domyślnie low; "" = domyślny modelu
  POZIOMKA_STT_URL     http://127.0.0.1:8001/v1   stt_canary/server.py
  POZIOMKA_TTS_URL     http://127.0.0.1:8002/v1   tts_voxcpm2/server.py (głos domyślny: glosy/poziomka.wav)

Koniec tury: Silero + przerwa w mowie (SpeechTimeoutUserTurnStopStrategy); semantyczne detektory końca
tury nie mają potwierdzonego polskiego. Przerwa jest dłuższa niż w zwykłej rozmowie (BOT_CISZA, domyślnie
1,2 s), bo przy odpowiadaniu na pytania ludzie robią pauzy na zastanowienie.

Echo: przy głośnikach echo cancellation przeglądarki nie wystarcza i Canary transkrybuje głos bota
jako wypowiedź użytkownika, co przerywa jego odpowiedź. Dlatego domyślnie mikrofon jest wyciszony, gdy
bot mówi (bez przerywania w pół zdania). BOT_PRZERYWANIE=1 włącza przerywanie — do rozmowy w słuchawkach.
"""
import os

from loguru import logger
from openai import OpenAI
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndFrame, LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.text.transforms.strip_markdown import strip_markdown
from pipecat.workers.runner import WorkerRunner

import pytania
import strona

STT_URL = os.environ.get("POZIOMKA_STT_URL", "http://127.0.0.1:8001/v1")
TTS_URL = os.environ.get("POZIOMKA_TTS_URL", "http://127.0.0.1:8002/v1")
TTS_SAMPLE_RATE = 48000  # VoxCPM2
MODEL = os.environ.get("PYTAJNIK_MODEL", "openai/gpt-6.1-sol")
REASONING = os.environ.get("PYTAJNIK_REASONING", "low")
PRZERYWANIE = os.environ.get("BOT_PRZERYWANIE", "0") == "1"
CISZA = float(os.environ.get("BOT_CISZA", "1.2"))

# Sprawdzane przy starcie, żeby zły plik albo brak klucza wyszły od razu, a nie przy pierwszym połączeniu.
pytania.wczytaj_env()
if not os.environ.get("OPENROUTER_API_KEY"):
    raise SystemExit("Ustaw OPENROUTER_API_KEY w .env (https://openrouter.ai/keys)")
CLIENT = OpenAI(base_url=pytania.OPENROUTER_URL, api_key=os.environ["OPENROUTER_API_KEY"])
DOMYSLNY = pytania.wczytaj(os.environ["PYTANIA"], CLIENT, MODEL) if os.environ.get("PYTANIA") else None
zestaw_polaczenia = strona.zainstaluj(CLIENT, MODEL, DOMYSLNY)
logger.info(f"Model {MODEL}, domyślny zestaw: {os.environ.get('PYTANIA') or 'brak'}")
BRAK_PYTAN = "Nie mam jeszcze pytań. Wgraj je na stronie startowej i połącz się ponownie."

transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments, zid: str | None):
    stt = OpenAISTTService(
        api_key="brak", base_url=STT_URL,
        settings=OpenAISTTService.Settings(model="canary-1b-v2", language=Language.PL),
    )
    llm = OpenRouterLLMService(
        api_key=os.environ["OPENROUTER_API_KEY"],
        settings=OpenRouterLLMService.Settings(
            # GPT 6.x nie przyjmuje temperature; reasoning tokeny liczą się do limitu, więc bez max_tokens.
            model=MODEL, system_instruction=pytania.prompt_systemowy(pytania.lista(zid)) if zid else "",
            extra={"extra_body": {"reasoning": {"effort": REASONING}}} if REASONING else {},
        ),
    )
    tts = OpenAITTSService(
        api_key="brak", base_url=TTS_URL, sample_rate=TTS_SAMPLE_RATE,
        # "alloy" to tylko nazwa wymagana przez klienta; serwer podstawia głos domyślny (poziomka).
        settings=OpenAITTSService.Settings(model="voxcpm2", voice="alloy", language=Language.PL),
        text_transforms=[("*", strip_markdown)],  # na wypadek **pogrubień** i list mimo promptu
    )

    # Model zaczyna sam (powitanie i pierwsze pytanie); część API wymaga choć jednej wiadomości użytkownika.
    context = LLMContext(messages=[{"role": "user", "content": "Zaczynajmy."}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.3)),
            user_turn_strategies=UserTurnStrategies(stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=CISZA)]),
            user_mute_strategies=[] if PRZERYWANIE else [AlwaysUserMuteStrategy()],
        ),
    )
    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_out_sample_rate=TTS_SAMPLE_RATE, enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Klient połączony (przerywanie: {'tak' if PRZERYWANIE else 'nie, mikrofon wyciszany gdy bot mówi'})")
        if zid:
            logger.info(f"Zestaw {pytania.zestaw(zid)['nazwa']} ({zid[:8]})")
            await worker.queue_frames([LLMRunFrame()])
        else:
            await worker.queue_frames([TTSSpeakFrame(BRAK_PYTAN), EndFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Klient rozłączony")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    zid = zestaw_polaczenia()  # przed pierwszym await: ciasteczko z żądania /api/offer (bot/strona.py)
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args, zid)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
