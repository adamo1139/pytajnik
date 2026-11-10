#!/usr/bin/env python3
"""Przepytywanie w terminalu, bez głosu i GPU: ten sam prompt i model co bot/bot.py.

  PYTANIA=pytania/podatki.txt .venv-bot/bin/python testy/test_tekst.py      # klucz z .env

Służy do sprawdzenia pliku z pytaniami i zachowania modelu (oceny, wskazówki) przed uruchomieniem bota.
Pusta linia, Ctrl+D albo Ctrl+C kończy.
"""
import os
import sys

from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
import pytania  # noqa: E402

pytania.wczytaj_env()
MODEL = os.environ.get("PYTAJNIK_MODEL", "openai/gpt-6.1-sol")
REASONING = os.environ.get("PYTAJNIK_REASONING", "low")


def main():
    client = OpenAI(base_url=pytania.OPENROUTER_URL, api_key=os.environ["OPENROUTER_API_KEY"])
    lista = pytania.lista(pytania.wczytaj(os.environ["PYTANIA"], client, MODEL))
    messages = [
        {"role": "system", "content": pytania.prompt_systemowy(lista)},
        {"role": "user", "content": "Zaczynajmy."},
    ]
    extra = {"reasoning": {"effort": REASONING}} if REASONING else {}
    while True:
        r = client.chat.completions.create(model=MODEL, messages=messages, extra_body=extra)
        tekst = r.choices[0].message.content
        print(f"\nPytajnik: {tekst}\n")
        messages.append({"role": "assistant", "content": tekst})
        try:
            odp = input("Ty: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not odp:
            break
        messages.append({"role": "user", "content": odp})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # Ctrl+C w trakcie odpowiedzi modelu
        print()
