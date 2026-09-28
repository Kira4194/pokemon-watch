"""Veille des prix de cartes Pokémon, tout en euros.

- Chaque jour : vérifie les prix cibles de chaque carte (alerte Telegram immédiate).
- Le lundi et le jeudi : envoie le récapitulatif des prix + variation en %
  par rapport au dernier récapitulatif envoyé, avec le prix PSA 10.

Sources de prix, dans l'ordre :
1. API Pokémon TCG (Cardmarket en € + TCGplayer en $)
2. TCGdex (secours si la 1re n'a pas encore de prix pour la carte)
3. PokemonPriceTracker (second secours, prix TCGplayer, nécessite une clé)
"""
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CARDS_FILE = Path("cards.csv")
HISTORY_FILE = Path("history.csv")
STATE_FILE = Path("state.json")
SUMMARY_DAYS = {0, 3}  # 0 = lundi, 3 = jeudi
API_URL = "https://api.pokemontcg.io/v2/cards/"
TCGDEX_URL = "https://api.tcgdex.net/v2/en/cards"
FX_URL = "https://api.frankfurter.app/latest?from=USD&to=EUR"

API_KEY = os.environ.get("POKEMONTCG_API_KEY", "")
PPT_URL = "https://www.pokemonpricetracker.com/api/v2/cards"
PPT_KEY = os.environ.get("POKEPRICETRACKER_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


# ---------- Outils ----------
def fmt_eur(x):
    s = f"{x:,.2f}".replace(",", "\u202f").replace(".", ",")
    return f"{s} €"


def parse_float(value):
    value = (value or "").strip().replace(",", ".")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram non configuré, message affiché ici :\n" + text + "\n")
        return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text[:4000]}).encode()
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=30
    )


def load_state():
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = {}
    for key in ("summary", "targets", "ppt_ids"):
        state.setdefault(key, {})
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- Taux de change USD -> EUR ----------
def get_usd_eur_rate():
    try:
        with urllib.request.urlopen(FX_URL, timeout=30) as resp:
            return float(json.load(resp)["rates"]["EUR"])
    except Exception as exc:
        print(f"Taux de change indisponible : {exc}")
        return None


# ---------- Source 1 : API Pokémon TCG ----------
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


def extract_prices_eur(card, usd_eur):
    """Tous les prix disponibles, convertis en euros."""
    prices = {}
    cm = (card.get("cardmarket") or {}).get("prices") or {}
    if cm.get("trendPrice"):
        prices["Cardmarket tendance"] = float(cm["trendPrice"])
    if cm.get("avg30"):
        prices["Cardmarket moyenne 30 j"] = float(cm["avg30"])
    if usd_eur:
        tp = (card.get("tcgplayer") or {}).get("prices") or {}
        for variant, data in tp.items():
            if data.get("market"):
                prices[f"TCGplayer {variant} (converti)"] = float(data["market"]) * usd_eur
    return prices


# ---------- Source 2 : TCGdex (secours, gratuit, sans clé) ----------
def tcgdex_get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except Exception as exc:
            print(f"TCGdex : tentative {attempt + 1} échouée ({url}) : {exc}")
            time.sleep(3 * (attempt + 1))
    return None


def tcgdex_prices(card, usd_eur):
    """Prix en euros depuis TCGdex. Complète aussi card[...] avec la date de mise à jour."""
    name = card.get("name", "")
    number = str(card.get("number", "")).lstrip("0")
    set_name = ((card.get("set") or {}).get("name") or "").lower()
    if not name or not number:
        return {}
    listing = tcgdex_get(TCGDEX_URL + "?" + urllib.parse.urlencode({"name": name}))
    for brief in listing or []:
        if str(brief.get("localId", "")).lstrip("0") != number:
            continue
        detail = tcgdex_get(TCGDEX_URL + "/" + urllib.parse.quote(str(brief.get("id", ""))))
        if not detail:
            continue
        found_set = ((detail.get("set") or {}).get("name") or "").lower()
        if not (set_name in found_set or found_set in set_name):
            continue
        pricing = detail.get("pricing") or {}
        prices = {}
        cm = pricing.get("cardmarket") or {}
        if cm.get("unit", "EUR") == "EUR":
            trend = cm.get("trend-holo") or cm.get("trend")
            avg30 = cm.get("avg30-holo") or cm.get("avg30")
            if trend:
                prices["Cardmarket tendance"] = float(trend)
            if avg30:
                prices["Cardmarket moyenne 30 j"] = float(avg30)
            card["cardmarket"] = {"updatedAt": str(cm.get("updated", ""))[:10]}
        tp = pricing.get("tcgplayer") or {}
        if usd_eur:
            for variant, data in tp.items():
                if isinstance(data, dict) and data.get("marketPrice"):
                    prices[f"TCGplayer {variant} (converti)"] = float(data["marketPrice"]) * usd_eur
            if tp:
                card["tcgplayer"] = {"updatedAt": str(tp.get("updated", ""))[:10]}
        if prices:
            print(f"Prix trouvés via TCGdex pour {name} {number}")
        return prices
    return {}


# ---------- Source 3 : PokemonPriceTracker (PSA 10 + prix de secours) ----------
def ppt_get(params):
    url = PPT_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {PPT_KEY}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp).get("data") or []
        except urllib.error.HTTPError as exc:
            print(f"PokemonPriceTracker : erreur HTTP {exc.code} ({params})")
            if exc.code in (401, 403, 429):  # clé refusée / accès non inclus / quota
                return None
        except Exception as exc:
            print(f"PokemonPriceTracker : tentative {attempt + 1} échouée : {exc}")
        time.sleep(5 * (attempt + 1))
    return None


_ppt_cache = {}


def ppt_card(state, card, card_id):
    """Fiche PokemonPriceTracker avec ventes eBay. Retourne (données, problème)."""
    if card_id not in _ppt_cache:
        _ppt_cache[card_id] = _ppt_lookup(state, card, card_id)
    return _ppt_cache[card_id]


def _ppt_lookup(state, card, card_id):
    if not PPT_KEY:
        return None, "nokey"
    ppt_id = state["ppt_ids"].get(card_id)
    if not ppt_id:
        number = str(card.get("number", "")).lstrip("0")
        set_name = (card.get("set") or {}).get("name", "")
        results = ppt_get({"search": f"{card.get('name', '')} {set_name}", "limit": 10})
        if results is None:
            return None, "refused"
        for r in results:
            same_number = str(r.get("cardNumber", "")).split("/")[0].lstrip("0") == number
            same_set = set_name.lower() in str(r.get("setName", "")).lower()
            if same_number and same_set:
                ppt_id = r.get("tcgPlayerId")
                break
        if not ppt_id:
            return None, "notfound"
        state["ppt_ids"][card_id] = ppt_id
    data = ppt_get({"tcgPlayerId": ppt_id, "includeEbay": "true"})
    if data is None:
        return None, "refused"
    return (data[0] if data else {}), None


def ppt_market_prices(state, card, card_id, usd_eur):
    data, problem = ppt_card(state, card, card_id)
    market = ((data or {}).get("prices") or {}).get("market")
    if problem or not market or not usd_eur:
        return {}
    return {"TCGplayer (via PokemonPriceTracker, converti)": float(market) * usd_eur}


def get_psa10_line(state, card, card_id, usd_eur):
    """Une ligne de texte sur le prix PSA 10 (ventes eBay), en euros."""
    data, problem = ppt_card(state, card, card_id)
    if problem == "nokey":
        return " • PSA 10 : clé PokemonPriceTracker non ajoutée dans les secrets GitHub"
    if problem == "refused":
        return " • PSA 10 : indisponible aujourd'hui (clé refusée ou quota atteint)"
    if problem == "notfound":
        return " • PSA 10 : carte introuvable chez PokemonPriceTracker"
    psa10 = ((data.get("ebay") or {}).get("salesByGrade") or {}).get("psa10") or {}
    price_usd = psa10.get("medianPrice") or psa10.get("averagePrice")
    if not price_usd or not psa10.get("count"):
        return " • PSA 10 : pas encore de ventes eBay enregistrées"
    if not usd_eur:
        return " • PSA 10 : taux de change indisponible"
    last = str(psa10.get("lastSaleDate", ""))[:10]
    line = (
        f" • PSA 10 (ventes eBay, converti en €) : {fmt_eur(price_usd * usd_eur)} "
        f"(médiane de {psa10['count']} vente(s)"
    )
    return line + (f", dernière le {last})" if last else ")")


# ---------- Liens et plateformes ----------
def ebay_psa10_link(card):
    set_info = card.get("set") or {}
    total = set_info.get("printedTotal")
    number = card.get("number", "")
    ref = f"{number}/{total}" if total else number
    query = urllib.parse.quote_plus(f"{card.get('name', '')} {ref} PSA 10")
    return f"https://www.ebay.fr/sch/i.html?_nkw={query}&LH_Sold=1&LH_Complete=1"


def link_for(card, key):
    url = (card.get(key) or {}).get("url")
    if not url and key == "cardmarket":
        query = urllib.parse.quote_plus(f"{card.get('name', '')} {card.get('number', '')}")
        url = f"https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString={query}"
    return url


def platform_info(card, source):
    """Plateforme, lien et date de mise à jour correspondant à une source de prix."""
    if source.startswith("Cardmarket"):
        key, name = "cardmarket", "Cardmarket (Europe, prix en euros)"
    else:
        key, name = "tcgplayer", "TCGplayer (États-Unis, prix en dollars convertis en euros)"
    return name, link_for(card, key), (card.get(key) or {}).get("updatedAt")


def reference_price(prices):
    """Prix utilisé pour les prix cibles : Cardmarket tendance, sinon TCGplayer converti."""
    if "Cardmarket tendance" in prices:
        return "Cardmarket tendance", prices["Cardmarket tendance"]
    tcg = {k: v for k, v in prices.items() if k.startswith("TCGplayer")}
    if tcg:
        source = max(tcg, key=tcg.get)
        return source, tcg[source]
    return None, None


# ---------- Programme principal ----------
def main():
    now = datetime.now(ZoneInfo("Europe/Paris"))
    today = now.date().isoformat()
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    send_summary = manual or now.weekday() in SUMMARY_DAYS

    state = load_state()
    usd_eur = get_usd_eur_rate()

    with CARDS_FILE.open(newline="", encoding="utf-8") as f:
        cards = [r for r in csv.DictReader(f) if (r.get("nom") or "").strip()]

    history_rows, alerts, blocks, problems = [], [], [], []
    new_summary = {}

    for row in cards:
        label = row["nom"].strip()
        card = fetch_card(row)
        if not card:
            problems.append(f"⚠️ {label} : carte introuvable ou API indisponible")
            continue
        card_id = card["id"]

        # Prix : source 1, puis secours 2 et 3
        fallback_note = None
        prices = extract_prices_eur(card, usd_eur)
        if not prices:
            prices = tcgdex_prices(card, usd_eur)
            if prices:
                fallback_note = "ℹ️ Prix issus de TCGdex (l'API principale n'a pas encore de prix pour cette carte)."
        if not prices:
            prices = ppt_market_prices(state, card, card_id, usd_eur)
            if prices:
                fallback_note = "ℹ️ Prix TCGplayer issus de PokemonPriceTracker (les autres sources n'ont pas encore de prix)."
        if not prices:
            problems.append(f"⚠️ {label} : aucune source n'a encore de prix pour cette carte")
            continue

        for source, price in prices.items():
            history_rows.append([today, card_id, label, source, round(price, 2)])

        # --- Prix cibles (vérifiés à chaque passage) ---
        ref_source, ref = reference_price(prices)
        low, high = parse_float(row.get("prix_bas")), parse_float(row.get("prix_haut"))
        status = "between"
        if low is not None and ref <= low:
            status = "below"
        elif high is not None and ref >= high:
            status = "above"
        if status != "between" and status != state["targets"].get(card_id):
            platform, url, updated = platform_info(card, ref_source)
            if status == "below":
                headline = f"Sous ton prix cible bas de {fmt_eur(low)} : {fmt_eur(ref)}"
            else:
                headline = f"Prix cible de {fmt_eur(high)} atteint : {fmt_eur(ref)}"
            msg = f"🎯 {label}\n{headline}\nSource : {platform}, {ref_source}"
            if updated:
                msg += f"\nDonnée mise à jour le : {updated}"
            if url:
                msg += f"\nLien : {url}"
            alerts.append(msg)
        state["targets"][card_id] = status

        # --- Récapitulatif : variation depuis le dernier récapitulatif envoyé ---
        prev_prices = state["summary"].get(card_id, {})
        lines = []
        for source, price in prices.items():
            prev = prev_prices.get(source)
            if prev:
                pct = (price - prev) / prev * 100
                lines.append(f" • {source} : {fmt_eur(price)} ({pct:+.1f} %)".replace(".", ","))
            else:
                lines.append(f" • {source} : {fmt_eur(price)} (première mesure)")
        for name, key in (("Cardmarket", "cardmarket"), ("TCGplayer", "tcgplayer")):
            if not any(src.startswith(name) for src in prices):
                continue  # pas de lien vers une plateforme dont on n'a pas de prix
            url = link_for(card, key)
            if url:
                lines.append(f" 🔗 {name} : {url}")
        if send_summary:
            lines.append(get_psa10_line(state, card, card_id, usd_eur))
            lines.append(f" 🔗 Ventes eBay PSA 10 : {ebay_psa10_link(card)}")
        if fallback_note:
            lines.append(f" {fallback_note}")
        blocks.append(f"{label}\n" + "\n".join(lines))
        new_summary[card_id] = prices
        time.sleep(1)

    # Historique complet (un fichier CSV)
    is_new = not HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "card_id", "name", "source", "price_eur"])
        writer.writerows(history_rows)

    # Alertes de prix cibles : envoyées tout de suite
    for alert in alerts:
        send_telegram(alert)

    # Récapitulatif du lundi et du jeudi
    if send_summary:
        parts = [f"📊 Prix des cartes — {now.strftime('%d/%m/%Y')}"]
        if usd_eur is None:
            parts.append("⚠️ Taux de change indisponible : prix en dollars ignorés cette fois.")
        parts += blocks + problems
        parts.append(
            "Cardmarket = Europe (prix en €). TCGplayer = États-Unis (prix en $ convertis en €). "
            "PSA 10 = ventes eBay.\nVariations par rapport au dernier récapitulatif."
        )
        send_telegram("\n\n".join(parts))
        state["summary"].update(new_summary)

    save_state(state)


if __name__ == "__main__":
    main()
