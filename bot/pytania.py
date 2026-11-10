"""Plik z pytaniami -> lista pytań -> prompt systemowy egzaminatora (pytania w losowej kolejności).

Plik może mieć dowolny format, np. tekst przekopiowany z PDF: pytania łamane na kilka linii, warianty
A/B/C w osobnych liniach, numery stron, nagłówki, klucz odpowiedzi na końcu. Model z OpenRouter wyciąga
z niego listę pytań (z wzorcowymi odpowiedziami, jeśli są w tekście). Wynik jest zapisywany w
dane/pytania/<sha256 tekstu>.json, więc ten sam tekst jest parsowany tylko raz; ten JSON można poprawić
ręcznie. sha256 tekstu to też id zestawu, którym strona (bot/strona.py) wybiera pytania dla urządzenia.

Najprostszy format, który zawsze działa: jedno pytanie w linii, opcjonalnie " | " i wzorcowa odpowiedź.

    Jaka jest stolica Australii? | Canberra
    Wyjaśnij, czym jest fotosynteza.
"""
import glob
import hashlib
import json
import os
import random
import re

from loguru import logger
from openai import OpenAI

KATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CACHE = os.path.join(KATALOG, "dane", "pytania")
OPENROUTER_URL = "https://openrouter.ai/api/v1"


def wczytaj_env():
    """Zmienne z .env w katalogu projektu (KLUCZ=wartość); te już ustawione w środowisku mają pierwszeństwo."""
    sciezka = os.path.join(KATALOG, ".env")
    if not os.path.exists(sciezka):
        return
    with open(sciezka, encoding="utf-8") as f:
        for linia in f:
            klucz, rowna, wartosc = linia.strip().partition("=")
            if rowna and klucz and not klucz.startswith("#") and wartosc:
                os.environ.setdefault(klucz.strip(), wartosc.strip().strip("\"'"))


EKSTRAKCJA = (
    "Dostajesz tekst z pytaniami, często przekopiowany z PDF. Wypisz wszystkie pytania, które da się z "
    "niego zadać, w kolejności z tekstu.\n"
    "- Przepisuj treść pytań wiernie. Napraw tylko artefakty kopiowania: łamanie linii w środku zdania, "
    "dzielenie wyrazów myślnikiem na końcu linii, numery stron, powtarzające się nagłówki i stopki.\n"
    "- Usuń numerację pytań. Warianty odpowiedzi (A, B, C…) dołącz do treści pytania w jednej linii, "
    "np. „Ile…? A) 5, B) 8, C) 23”.\n"
    "- Jeśli tekst podaje prawidłową odpowiedź (po „|”, „Odp.:”, w kluczu odpowiedzi na końcu, oznaczony "
    "wariant), wpisz ją do pola odpowiedz; przy pytaniach zamkniętych z literą i treścią wariantu. "
    "Nie wymyślaj odpowiedzi, których w tekście nie ma — wtedy odpowiedz to null.\n"
    "- Pomiń instrukcje, tytuły, punktację i inny tekst, który nie jest pytaniem."
)
SCHEMAT = {
    "name": "pytania",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "pytania": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"pytanie": {"type": "string"}, "odpowiedz": {"type": ["string", "null"]}},
                    "required": ["pytanie", "odpowiedz"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["pytania"],
        "additionalProperties": False,
    },
}


def wyciagnij(tekst: str, client: OpenAI, model: str, nazwa: str = "") -> str:
    """Wyciąga pytania z tekstu (albo bierze je z cache) i zwraca id zestawu (sha256 tekstu)."""
    if not tekst.strip():
        raise ValueError("pusty tekst")
    zid = hashlib.sha256(tekst.encode()).hexdigest()
    if os.path.exists(sciezka_zestawu(zid)):
        logger.info(f"Pytania z {sciezka_zestawu(zid)}")
        return zid
    logger.info(f"Wyciągam pytania ({nazwa or zid[:8]}) przez {model}…")
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": EKSTRAKCJA}, {"role": "user", "content": tekst}],
        response_format={"type": "json_schema", "json_schema": SCHEMAT},
        extra_body={"reasoning": {"effort": "low"}},
    )
    pytania = json.loads(r.choices[0].message.content)["pytania"]
    if not pytania:
        raise ValueError("model nie znalazł w tekście pytań")
    os.makedirs(CACHE, exist_ok=True)
    with open(sciezka_zestawu(zid), "w", encoding="utf-8") as f:
        json.dump({"nazwa": nazwa or pytania[0]["pytanie"][:60], "pytania": pytania}, f, ensure_ascii=False, indent=1)
    logger.info(f"{len(pytania)} pytań zapisanych w {sciezka_zestawu(zid)} (można poprawić ręcznie)")
    return zid


def sciezka_zestawu(zid: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", zid):
        raise ValueError(f"złe id zestawu: {zid!r}")
    return os.path.join(CACHE, zid + ".json")


def zestaw(zid: str) -> dict:
    """{"nazwa", "pytania": [{"pytanie", "odpowiedz"}]}; starsze pliki cache to sama lista pytań."""
    with open(sciezka_zestawu(zid), encoding="utf-8") as f:
        dane = json.load(f)
    return {"nazwa": zid[:8], "pytania": dane} if isinstance(dane, list) else dane


def zestawy() -> list[dict]:
    """Zapisane zestawy, od najnowszego: [{"id", "nazwa", "liczba"}]."""
    if not os.path.isdir(CACHE):
        return []
    pliki = sorted(glob.glob(os.path.join(CACHE, "*.json")), key=os.path.getmtime, reverse=True)
    wynik = []
    for plik in pliki:
        zid = os.path.basename(plik)[:-5]
        try:
            z = zestaw(zid)
        except (ValueError, json.JSONDecodeError):
            continue
        wynik.append({"id": zid, "nazwa": z["nazwa"], "liczba": len(z["pytania"])})
    return wynik


def lista(zid: str) -> list[tuple[str, str | None]]:
    """Pytania zestawu jako (pytanie, wzorcowa odpowiedź albo None) w kolejności z tekstu."""
    return [(p["pytanie"], p["odpowiedz"] or None) for p in zestaw(zid)["pytania"]]


def wczytaj(sciezka: str, client: OpenAI, model: str) -> str:
    """Plik z pytaniami -> id zestawu."""
    with open(sciezka, encoding="utf-8") as f:
        return wyciagnij(f.read(), client, model, nazwa=os.path.basename(sciezka))


def prompt_systemowy(pytania: list[tuple[str, str | None]], rng: random.Random | None = None) -> str:
    """Prompt z pytaniami w losowej kolejności; każde wywołanie (nowa rozmowa) losuje od nowa."""
    pytania = pytania[:]
    (rng or random).shuffle(pytania)
    lista = "\n".join(
        f"{i}. {p}" + (f"\n   Wzorcowa odpowiedź: {o}" if o else "") for i, (p, o) in enumerate(pytania, 1)
    )
    return (
        "Jesteś Pytajnikiem, polskim egzaminatorem głosowym. Przepytujesz użytkownika z pytań poniżej, "
        "dokładnie w tej kolejności, jedno pytanie naraz.\n\n"
        "Przebieg:\n"
        "- Na początku przywitaj się jednym zdaniem, powiedz, ile jest pytań, i od razu zadaj pierwsze.\n"
        "- Pytania zamknięte czytaj razem z wariantami odpowiedzi.\n"
        "- Po każdej odpowiedzi oceń ją krótko: dobrze, częściowo albo źle. Powiedz, co było trafne, a "
        "czego zabrakło lub co było błędne, i podaj prawidłową odpowiedź, jeśli użytkownik jej nie dał. "
        "Dodaj jedną praktyczną wskazówkę, jak to zapamiętać albo na co uważać. Potem zadaj następne pytanie.\n"
        "- Jeśli użytkownik nie wie, poprosi o podpowiedź albo powtórzenie, podpowiedz lub powtórz pytanie, "
        "ale nie zdradzaj od razu odpowiedzi. Gdy poprosi o przejście dalej, podaj odpowiedź i idź dalej.\n"
        "- Odpowiedzi są transkrybowane z mowy, więc wybaczaj literówki, liczby zapisane cyframi i "
        "drobne przekręcenia słów; oceniaj treść.\n"
        "- Wzorcowa odpowiedź, jeśli jest, rozstrzyga ocenę. Bez niej oceniaj według własnej wiedzy.\n"
        "- Po ostatnim pytaniu podsumuj: wynik w punktach (dobrze to jeden punkt, częściowo pół), "
        "z czym poszło dobrze i co warto powtórzyć. Potem zakończ.\n\n"
        "Styl: twoje wypowiedzi są czytane na głos. Mów naturalnie i zwięźle, ocena z wskazówką to "
        "zwykle dwa, trzy zdania. Nie używaj list, punktów, nagłówków, pogrubień, emoji ani wzorów. "
        "Liczby zapisuj tak, jak się je wymawia.\n\n"
        f"Pytania ({len(pytania)}):\n{lista}"
    )
