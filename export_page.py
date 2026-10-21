"""Prépare les données de la page « Cote de mes cartes Pokémon » à partir de history.csv.

Ce script ne cherche aucun prix : il relit seulement ce que track.py a déjà
enregistré, et produit page.json, que Claude recopie tel quel sur la page.

Pour chaque carte, le prix retenu est le même que pour les alertes Telegram
(fonction reference_price de track.py) : Cardmarket moyenne 7 jours si elle existe,
sinon Cardmarket tendance, sinon TCGplayer converti en euros.
"""
import csv
import json
from collections import defaultdict

# card_id de track.py  ->  identifiant de la carte sur la page
PAGE_IDS = {
    "30th-154": "ectoplasma-154",
    "30th-158": "mew-158",
    "30th-153": "nymphali-153",
    "30th-152": "mew-152",
    "me05-116": "mega-darkrai-116",
}
SOURCE_LABELS = {
    "Cardmarket moyenne 7 j": "Cardmarket, moyenne 7 jours (relevé GitHub)",
    "Cardmarket tendance": "Cardmarket, cote tendance (relevé GitHub)",
}


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


def main():
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

    with open("page.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for page_id, data in out.items():
        last = data["history"][-1]
        print(f"{page_id}: {last['v']} € le {last['d']} ({len(data['history'])} relevés)")


if __name__ == "__main__":
    main()
