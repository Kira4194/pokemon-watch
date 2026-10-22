"""Prix du jour de toutes les cartes du Pokédex (possédées ou manquantes).

Prix retenu : le prix de vente moyen Cardmarket (champ « avg »), c'est-à-dire la même
valeur que la « moyenne des ventes » affichée par PokéCardex. Il vient du guide des prix
officiel de Cardmarket (fichier public et gratuit, mis à jour chaque jour).

Entrée  : pokedex_ids.csv (set de la page, n° de la carte, idProduct Cardmarket)
Sortie  : pokedex_prices.json, que export_page.py recopie dans le Pokédex de la page
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cardmarket

IDS_FILE = Path("pokedex_ids.csv")
OUT_FILE = Path("pokedex_prices.json")


def main():
    today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
    guide_date, guide = cardmarket.load_price_guide()
    if not guide:
        print("Pokédex : guide des prix indisponible, pokedex_prices.json n'est pas modifié")
        return

    sets, missing = {}, []
    with IDS_FILE.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            price = cardmarket.average_sell_price(row["cardmarket_id"])
            if price is None:
                missing.append(f"{row['set']} {row['num']} {row['nom']}")
                continue
            sets.setdefault(row["set"], {})[str(int(row["n"]))] = round(price, 2)

    OUT_FILE.write_text(json.dumps({
        "date": today,
        "guide_date": guide_date,
        "source": "Cardmarket, prix de vente moyen (guide des prix officiel, relevé GitHub)",
        "sets": sets,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for set_id, prices in sets.items():
        print(f"Pokédex {set_id} : {len(prices)} prix")
    if missing:
        print(f"Pokédex : {len(missing)} carte(s) sans prix aujourd'hui : " + ", ".join(missing[:20]))


if __name__ == "__main__":
    main()
