"""Prépare les données de la page « Cote de mes cartes Pokémon ».

Ce script ne cherche aucun prix : il relit seulement ce que track.py (history.csv)
et pokedex.py (pokedex_prices.json) ont déjà enregistré.

Utilisation par la tâche Claude de copie quotidienne :

    python3 export_page.py --db DOSSIER

DOSSIER contient les documents actuels de la page, tels qu'ArtifactData les enregistre
avec out_dir : DOSSIER/cards/<id>.json (vitrine) et DOSSIER/sets/<id>.json (Pokédex).
Le script écrit dans DOSSIER/out/ un fichier JSON par document à mettre à jour, plus
DOSSIER/out/writes.json : la liste des écritures à faire en une seule action « batch ».

Vitrine : prix = Cardmarket moyenne 7 jours (même prix que les alertes Telegram).
Pokédex : prix = prix de vente moyen Cardmarket (comme PokéCardex), sauf pour les cartes
de la vitrine, qui gardent leur moyenne 7 jours pour avoir le même prix partout.

Sans --db, écrit seulement page.json (ancien fonctionnement).
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

# card_id de track.py -> identifiant de la carte sur la page
PAGE_IDS = {
    "30th-154": "ectoplasma-154",
    "30th-158": "mew-158",
    "30th-153": "nymphali-153",
    "30th-152": "mew-152",
    "me05-116": "mega-darkrai-116",
}
# carte de la vitrine -> (set du Pokédex, numéro n de la carte dans ce set)
POKEDEX_SLOTS = {
    "ectoplasma-154": ("30C", 154),
    "mew-158": ("30C", 158),
    "nymphali-153": ("30C", 153),
    "mew-152": ("30C", 152),
    "mega-darkrai-116": ("NN", 116),
}
SOURCE_LABELS = {
    "Cardmarket moyenne 7 j": "Cardmarket, moyenne 7 jours (relevé GitHub)",
    "Cardmarket tendance": "Cardmarket, cote tendance (relevé GitHub)",
}
AVG7_PREFIX = "Cardmarket, moyenne 7 jours"


def card_id(row):
    set_code = {"30th": "30th", "Pitch Black": "me05"}.get(row["mot_set"], row["mot_set"])
    return f"{set_code}-{row['numero']}"


def reference(prices):
    if "Cardmarket moyenne 7 j" in prices:
        return "Cardmarket moyenne 7 j", prices["Cardmarket moyenne 7 j"]
    if "Cardmarket tendance" in prices:
        return "Cardmarket tendance", prices["Cardmarket tendance"]
    for source, value in prices.items():
        if source.startswith("TCGplayer"):
            return source, value
    return None, None


def vitrine():
    """Champs à mettre à jour pour chaque carte de la vitrine, d'après history.csv."""
    targets = {}
    with open("cards.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            high = (row.get("prix_haut") or "").strip()
            targets[card_id(row)] = float(high) if high else None

    by_day = defaultdict(lambda: defaultdict(dict))  # card -> date -> {source: prix}
    with open("history.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                by_day[row["card_id"]][row["date"]][row["source"]] = float(row["price_eur"])
            except (KeyError, ValueError):
                continue

    out = {}
    for cid, page_id in PAGE_IDS.items():
        days = by_day.get(cid, {})
        history, last_source, avg30, avg7 = [], None, None, None
        for day in sorted(days):
            source, value = reference(days[day])
            if value is None:
                continue
            history.append({"d": day, "v": round(value, 2), "s": source})
            last_source = source
            avg30 = days[day].get("Cardmarket moyenne 30 j", avg30 if source.startswith("Cardmarket") else None)
            avg7 = days[day].get("Cardmarket moyenne 7 j")
        if not history:
            continue
        # Courbe homogène : on ne garde que les relevés de la même source que le dernier
        history = [{"d": h["d"], "v": h["v"]} for h in history if h["s"] == last_source]
        label = SOURCE_LABELS.get(last_source) or "TCGplayer, prix marché converti en € (relevé GitHub)"
        out[page_id] = {
            "history": history,
            "source": label,
            "target": targets.get(cid),
            "avg30": round(avg30, 2) if avg30 is not None else {"__delete__": True},
            "avg7": round(avg7, 2) if avg7 is not None else {"__delete__": True},
            "lowFrNm": {"__delete__": True},
            "fx": {"__delete__": True},
        }
    return out


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", help="dossier des documents actuels de la page (cards/ et sets/)")
    args = parser.parse_args()

    cards = vitrine()
    if not args.db:
        write_json(Path("page.json"), cards)
        for page_id, data in cards.items():
            last = data["history"][-1]
            print(f"{page_id}: {last['v']} € le {last['d']} ({len(data['history'])} relevés)")
        return

    db = Path(args.db)
    dest = db / "out"
    writes, kept, ignored = [], {}, []

    # --- Vitrine : seulement les cartes qui ont la moyenne 7 jours Cardmarket ---
    for page_id, data in cards.items():
        current_file = db / "cards" / f"{page_id}.json"
        if not data["source"].startswith(AVG7_PREFIX) or not current_file.exists():
            ignored.append(page_id)
            continue
        current = json.loads(current_file.read_text(encoding="utf-8"))
        merged = {}
        if str(current.get("source", "")).startswith(AVG7_PREFIX):
            for h in current.get("history") or []:
                if isinstance(h, dict) and "d" in h and "v" in h:
                    merged[h["d"]] = h["v"]
        merged.update({h["d"]: h["v"] for h in data["history"]})
        data["history"] = [{"d": d, "v": merged[d]} for d in sorted(merged)]
        path = dest / "cards" / f"{page_id}.json"
        write_json(path, data)
        writes.append({"op": "update", "collection": "cards", "doc_id": page_id, "file_path": str(path.resolve())})
        kept[page_id] = data["history"][-1]

    # --- Pokédex : prix du jour de toutes les cartes, possédées ou manquantes ---
    pokedex = {}
    if Path("pokedex_prices.json").exists():
        pokedex = json.loads(Path("pokedex_prices.json").read_text(encoding="utf-8"))
    set_prices = pokedex.get("sets") or {}
    pokedex_done = []
    for set_file in sorted((db / "sets").glob("*.json")):
        set_id = set_file.stem
        doc = json.loads(set_file.read_text(encoding="utf-8"))
        new_prices = set_prices.get(set_id, {})
        overrides = {n: kept[pid]["v"] for pid, (sid, n) in POKEDEX_SLOTS.items() if sid == set_id and pid in kept}
        if not new_prices and not overrides:
            continue
        new_cards = []
        for c in doc.get("cards") or []:
            c = dict(c)  # on garde tous les champs, en particulier « own »
            n = c.get("n")
            value = overrides.get(n, new_prices.get(str(n)))
            if value is not None:
                c["price"] = value
            new_cards.append(c)
        payload = {"cards": new_cards}
        if new_prices:
            payload["priceDate"] = pokedex.get("date")
            payload["priceSource"] = pokedex.get("source")
        path = dest / "sets" / f"{set_id}.json"
        write_json(path, payload)
        writes.append({"op": "update", "collection": "sets", "doc_id": set_id, "file_path": str(path.resolve())})
        pokedex_done.append(f"{set_id} ({len(new_prices)} prix)")

    write_json(dest / "writes.json", writes)

    dates = [h["d"] for h in kept.values()] + ([pokedex["date"]] if pokedex.get("date") else [])
    print(f"DERNIER_RELEVE={max(dates) if dates else 'aucun'}")
    print("VITRINE=" + (", ".join(f"{k} {v['v']} € ({v['d']})" for k, v in kept.items()) or "rien"))
    print("EN_ATTENTE_MOYENNE_7J=" + (", ".join(ignored) or "aucune"))
    print("POKEDEX=" + (", ".join(pokedex_done) or "rien") + (f" — prix du {pokedex.get('date')}" if pokedex.get("date") else ""))
    print(f"ECRITURES={len(writes)} (liste dans {dest / 'writes.json'})")


if __name__ == "__main__":
    main()
