"""Prépare le brouillon Gmail que la page « Cote de mes cartes Pokémon » lit à l'ouverture.

Ce script ne cherche aucun prix : il relit history.csv et pokedex_prices.json
(déjà écrits par track.py et pokedex.py) grâce à export_page.py.

    python3 export_draft.py

Écrit draft_body.txt (texte à mettre tel quel dans le corps du brouillon) et affiche
SUJET, DERNIER_RELEVE et TAILLE. Le JSON ne contient aucun espace, pour que la page
puisse retirer sans risque les retours à la ligne que Gmail ajouterait. La ligne
« check= » est une empreinte : la page ignore le brouillon s'il a été mal recopié.
"""
import hashlib
import json
from pathlib import Path

import export_page

HISTORY_DAYS = 15  # derniers relevés envoyés par carte de la vitrine


def number(value):
    value = round(float(value), 2)
    return int(value) if value.is_integer() else value


def main():
    vitrine = {}
    for page_id, data in export_page.vitrine().items():
        if not data["source"].startswith(export_page.AVG7_PREFIX):
            continue  # la vitrine n'affiche que la moyenne 7 jours Cardmarket
        entry = {"h": [[h["d"], number(h["v"])] for h in data["history"][-HISTORY_DAYS:]]}
        for key, short in (("avg7", "a7"), ("avg30", "a30"), ("target", "t")):
            if isinstance(data.get(key), (int, float)):
                entry[short] = number(data[key])
        vitrine[page_id] = entry

    pokedex = {}
    if Path("pokedex_prices.json").exists():
        pokedex = json.loads(Path("pokedex_prices.json").read_text(encoding="utf-8"))
    prices = {}
    for set_id, by_n in (pokedex.get("sets") or {}).items():
        size = max((int(n) for n in by_n), default=0)
        prices[set_id] = [number(by_n[str(n)]) if str(n) in by_n else None for n in range(1, size + 1)]

    dates = [e["h"][-1][0] for e in vitrine.values() if e["h"]]
    if pokedex.get("date"):
        dates.append(pokedex["date"])
    date = max(dates) if dates else "aucun"

    payload = {
        "v": 1,
        "date": date,
        "pd": pokedex.get("date"),
        "vit": vitrine,
        "slots": {pid: [sid, n] for pid, (sid, n) in export_page.POKEDEX_SLOTS.items()},
        "p": prices,
    }
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    assert " " not in text
    check = hashlib.sha256(text.encode("ascii")).hexdigest()[:16]
    body = f"pokemon-watch v1\n{text}\ncheck={check}\n"
    Path("draft_body.txt").write_text(body, encoding="ascii")
    print(f"SUJET=pokemon-watch prix {date}")
    print(f"DERNIER_RELEVE={date}")
    print(f"TAILLE={len(body)} caractères")


if __name__ == "__main__":
    main()
