"""Veille des prix de cartes Pokémon (API Pokémon TCG) + alerte Telegram."""
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CARDS_FILE = Path("cards.csv")
HISTORY_FILE = Path("history.csv")
DEFAULT_THRESHOLD = 10.0  # % de variation à partir duquel on alerte
API_URL = "https://api.pokemontcg.io/v2/cards/"

API_KEY = os.environ.get("POKEMONTCG_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def api_get(url):
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(4):  # l'API est parfois lente : on réessaie
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)["data"]
        except Exception as exc:
            print(f"Tentative {attempt + 1} échouée ({url}) : {exc}")
            time.sleep(5 * (attempt + 1))
    return None


def fetch_card(row):
    """Trouve la carte par id, ou par nom anglais + numéro + mot du set."""
    card_id = (row.get("id") or "").strip()
    if card_id:
        return api_get(API_URL + urllib.parse.quote(card_id))

    name = (row.get("nom_anglais") or "").strip()
    number = (row.get("numero") or "").strip()
    set_word = (row.get("mot_set") or "").strip().lower()
    query = f'name:"{name}" number:{number}'
    results = api_get(API_URL + "?" + urllib.parse.urlencode({"q": query, "pageSize": 30}))
    for card in results or []:
        card_set = card.get("set", {})
        haystack = f"{card_set.get('name', '')} {card_set.get('id', '')}".lower()
        if set_word in haystack:
            print(f"Trouvé : {card['id']} ({card_set.get('name')})")
            return card
    print(f"Aucune carte trouvée pour {query} (set contenant '{set_word}')")
    return None


def extract_prices(card):
    prices = {}
    cm = (card.get("cardmarket") or {}).get("prices") or {}
    if cm.get("trendPrice"):
        prices["Cardmarket tendance (€)"] = cm["trendPrice"]
    if cm.get("avg30"):
        prices["Cardmarket moyenne 30j (€)"] = cm["avg30"]
    tp = (card.get("tcgplayer") or {}).get("prices") or {}
    for variant, data in tp.items():
        if data.get("market"):
            prices[f"TCGplayer {variant} ($)"] = data["market"]
    return prices


def load_last_prices():
    last = {}
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                last[(row["card_id"], row["source"])] = float(row["price"])
    return last


def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram non configuré, message affiché ici :\n" + text)
        return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text[:4000]}).encode()
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=30
    )


def main():
    today = date.today().isoformat()
    last = load_last_prices()
    new_rows, movers, overview = [], [], []

    with CARDS_FILE.open(newline="", encoding="utf-8") as f:
        cards = [r for r in csv.DictReader(f) if r.get("nom")]

    for row in cards:
        label = row["nom"].strip()
        try:
            threshold = float(row.get("seuil_pct") or DEFAULT_THRESHOLD)
        except ValueError:
            threshold = DEFAULT_THRESHOLD

        card = fetch_card(row)
        if not card:
            overview.append(f"⚠️ {label} : introuvable ou API indisponible")
            continue
        card_id = card["id"]

        for source, price in extract_prices(card).items():
            new_rows.append([today, card_id, label, source, price])
            prev = last.get((card_id, source))
            if prev:
                pct = (price - prev) / prev * 100
                line = f"{label} — {source} : {prev:.2f} → {price:.2f} ({pct:+.1f} %)"
                overview.append(line)
                if abs(pct) >= threshold:
                    movers.append(("📈 " if pct > 0 else "📉 ") + line)
            else:
                overview.append(f"{label} — {source} : {price:.2f} (première mesure)")
        time.sleep(1)

    is_new = not HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "card_id", "name", "source", "price"])
        writer.writerows(new_rows)

    parts = [f"Veille cartes Pokémon — {today}"]
    if movers:
        parts.append("\nGros mouvements :\n" + "\n".join(movers))
    else:
        parts.append("\nAucun mouvement au-dessus du seuil.")
    parts.append("\nDétail :\n" + "\n".join(overview))
    send_telegram("\n".join(parts))


if __name__ == "__main__":
    main()
