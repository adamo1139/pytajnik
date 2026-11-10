# Pytajnik

Głosowy egzaminator po polsku. Dajesz plik tekstowy z pytaniami, a Pytajnik zadaje je na głos w losowej
kolejności, słucha odpowiedzi, mówi, co było dobrze, a co źle, daje wskazówkę i przechodzi do następnego
pytania. Na końcu podaje wynik i to, co warto powtórzyć.

Silero VAD v6 → Canary-1b-v2 (STT, lokalnie) → **openai/gpt-6.1-sol przez OpenRouter** → VoxCPM2 (TTS, lokalnie),
połączone przez [Pipecat](https://github.com/pipecat-ai/pipecat). STT i TTS razem zajmują ~8 GB VRAM.

## Plik z pytaniami

Dowolny tekst z pytaniami (UTF-8), także wklejony z PDF: pytania łamane na kilka linii, warianty A/B/C
w osobnych liniach, numery stron, klucz odpowiedzi na końcu. Przy pierwszym użyciu pliku model wyciąga z niego
listę pytań i zapisuje ją w `dane/pytania/<hash>.json` (można ją poprawić ręcznie; zmiana pliku = nowe parsowanie).
Jeśli tekst podaje prawidłowe odpowiedzi, model ocenia według nich, a bez nich według własnej wiedzy.

Najpewniejszy format: jedno pytanie w linii, po ` | ` wzorcowa odpowiedź.

```
Jaka jest stolica Australii? | Canberra
Wyjaśnij krótko, czym jest fotosynteza.
```

Przykłady: [pytania/przyklad.txt](pytania/przyklad.txt), [pytania/podatki.txt](pytania/podatki.txt) (VAT, PIT liniowy, CIT).

## Wymagania

- Linux x86_64, karta NVIDIA z ≥ 10 GB VRAM (testowane: RTX 5080).
- [uv](https://docs.astral.sh/uv/getting-started/installation/), `ffmpeg` (biblioteki dla torchcodec), `curl`.
- Klucz [OpenRouter](https://openrouter.ai/keys) w pliku `.env` (`OPENROUTER_API_KEY=...`) albo w zmiennej środowiskowej.

## Instalacja i uruchomienie

```
git clone https://github.com/adamo1139/pytajnik && cd pytajnik
bash setup_venvs.sh                                   # .venv-tts .venv-stt .venv-bot (~15 GB)
# mało miejsca? VENV_DIR=/inny/dysk bash setup_venvs.sh  — venvy tam, tu dowiązania .venv-*
echo 'OPENROUTER_API_KEY=sk-or-...' > .env                # klucz, plik jest w .gitignore
bash uruchom.sh [pytania/podatki.txt]                 # TTS -> STT -> bot, potem http://localhost:7860
bash zatrzymaj.sh
```

Na stronie http://localhost:7860 wkleja się własne pytania (albo wybiera zapisany zestaw) i przechodzi do
rozmowy (`/client`). Każde urządzenie ma własny wybrany zestaw (ciasteczko); bez wyboru dostaje plik podany
do `uruchom.sh`. Każde połączenie to nowa sesja z nowo wylosowaną kolejnością. Modele STT i TTS pobierają się
z Hugging Face przy pierwszym starcie.

Bez głosu i GPU, do sprawdzenia pliku i zachowania modelu:

```
PYTANIA=pytania/podatki.txt .venv-bot/bin/python testy/test_tekst.py
```

## Ustawienia (zmienne środowiskowe)

| zmienna | domyślnie | |
|---|---|---|
| `PYTAJNIK_MODEL` | `openai/gpt-6.1-sol` | dowolny model z OpenRouter |
| `PYTAJNIK_REASONING` | `low` | reasoning effort; pusty = domyślny modelu |
| `BOT_CISZA` | `1.2` | ile sekund ciszy kończy odpowiedź |
| `BOT_PRZERYWANIE` | `0` | `1` pozwala przerywać botowi — tylko w słuchawkach (inaczej echo) |

## Inne urządzenia w sieci

Bot słucha na całej sieci: `uruchom.sh` wypisuje adres typu `http://192.168.1.24:7860`. Dwie przeszkody:

- **Mikrofon przez http** jest dozwolony tylko na `localhost` (bez bezpiecznego kontekstu nie ma ani mikrofonu,
  ani AudioWorklet — prebuilt UI zgłasza wtedy „startLocalAudioLevelObserver() is not supported”). W Firefoksie
  na drugim urządzeniu: `about:config` → `dom.securecontext.allowlist` = `192.168.1.24` (adres komputera z botem).
  Na Androidzie `about:config` jest tylko w Firefox Beta i Nightly; na iPhonie bez HTTPS się nie da.
- **Zapora (ufw)**: potrzebny port 7860/tcp i losowe porty UDP WebRTC, np. `sudo ufw allow from 192.168.1.0/24`.
 Decyzje i historia projektu
(wcześniej asystent „Poziomka dostaje głos” z lokalnym LLM): [PLAN.md](PLAN.md).
