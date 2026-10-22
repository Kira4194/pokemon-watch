"""Veille des prix de cartes Pokémon, tout en euros.

- Chaque jour : vérifie les prix cibles de chaque carte (alerte Telegram immédiate).
- Le lundi et le jeudi : envoie le récapitulatif des prix + variation en %
  par rapport au dernier récapitulatif envoyé, avec le prix PSA 10.

Sources de prix, dans l'ordre :
1. Guide des prix Cardmarket (fichier public quotidien, en €), via la colonne
   cardmarket_id de cards.csv : moyenne 7 jours, tendance, moyenne 30 jours
2. TCGdex (prix TCGplayer, et Cardmarket si le guide n'a pas la carte)
3. API Pokémon TCG (secours, en fin de vie)
4. PokemonPriceTracker (second secours, prix TCGplayer, nécessite une clé)
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

import cardmarket

CARDS_FILE = Path("cards.csv")
HISTORY_FILE = Path("history.csv")
STATE_FILE = Path("state.json")
SUMMARY_DAYS = {0, 3}  # 0 = lundi, 3 = jeudi
API_URL = "https://api.pokemontcg.io/v2/cards/"
TCGDEX_URL = "https://api.tcgdex.net/v2/en/cards"
FX_URLS = [
    "https://api.frankfurter.app/latest?from=USD&to=EUR",
    "https://open.er-api.com/v6/latest/USD",
    "https://api.exchangerate-api.com/v4/latest/USD",
]
# Mot du set dans cards.csv -> code du set (sert d'identifiant de carte, ex. 30th-154)
SET_CODES = {"30th": "30th", "Pitch Black": "me05"}

API_KEY = os.environ.get("POKEMONTCG_API_KEY", "")
PPT_URL = "https://www.pokemonpricetracker.com/api/v2/cards"
PPT_KEY = os.environ.get("POKEPRICETRACKER_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


# ---------- Outils ----------
def fmt_eur(x):
    s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
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


def minimal_card(row):
    """Fiche minimale quand seules les données Cardmarket sont disponibles."""
    set_word = (row.get("mot_set") or "").strip()
    number = (row.get("numero") or "").strip()
    return {
        "id": f"{SET_CODES.get(set_word, set_word)}-{number}",
        "name": (row.get("nom_anglais") or "").strip(),
        "number": number,
        "set": {"name": set_word},
    }


# ---------- Taux de change USD -> EUR ----------
def get_usd_eur_rate():
    """Essaie plusieurs services l'un après l'autre (une adresse GitHub partagée
    peut se faire bloquer temporairement par l'un d'eux)."""
    for url in FX_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return float(json.load(resp)["rates"]["EUR"])
        except Exception as exc:
            print(f"Taux de change indisponible via {url} : {exc}")
    return None


# ---------- Secours : API Pokémon TCG ----------
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
    if cm.get("avg7"):
        prices["Cardmarket moyenne 7 j"] = float(cm["avg7"])
    if cm.get("avg30"):
        prices["Cardmarket moyenne 30 j"] = float(cm["avg30"])
    if usd_eur:
        tp = (card.get("tcgplayer") or {}).get("prices") or {}
        for variant, data in tp.items():
            if data.get("market"):
                prices[f"TCGplayer {variant} (converti)"] = float(data["market"]) * usd_eur
    return prices


# ---------- TCGdex (gratuit, sans clé) ----------
def tcgdex_get(url):
    # En-tête navigateur : sans lui, TCGdex renvoie parfois une fiche sans prix
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (pokemon-watch)", "Cache-Control": "no-cache"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception as exc:
            print(f"TCGdex : tentative {attempt + 1} échouée ({url}) : {exc}")
            time.sleep(3 * (attempt + 1))
    return None


def find_card_tcgdex(row):
    """Trouve la carte et ses prix directement via TCGdex (sans clé)."""
    name = (row.get("nom_anglais") or "").strip()
    number = (row.get("numero") or "").strip()
    set_word = (row.get("mot_set") or "").strip().lower()
    if not name or not number:
        return None
    listing = tcgdex_get(TCGDEX_URL + "?" + urllib.parse.urlencode({"name": name}))
    for brief in listing or []:
        if str(brief.get("localId", "")).lstrip("0") != number.lstrip("0"):
            continue
        detail = tcgdex_get(TCGDEX_URL + "/" + urllib.parse.quote(str(brief.get("id", ""))))
        if not detail:
            continue
        found_set = ((detail.get("set") or {}).get("name") or "")
        if set_word and set_word not in found_set.lower():
            continue
        card = {
            "id": detail.get("id"),
            "name": detail.get("name"),
            "number": detail.get("localId"),
            "set": {"name": found_set, "printedTotal": (detail.get("set") or {}).get("cardCount", {}).get("official")},
        }
        pricing = detail.get("pricing") or {}
        cm = pricing.get("cardmarket") or {}
        if cm:
            card["cardmarket"] = {"updatedAt": str(cm.get("updated", ""))[:10]}
        tp = pricing.get("tcgplayer") or {}
        if tp:
            card["tcgplayer"] = {"updatedAt": str(tp.get("updated", ""))[:10]}
        print(f"Trouvé via TCGdex : {card['id']} ({found_set})")
        return card
    print(f"TCGdex : carte introuvable pour {name} {number} (set contenant '{set_word}')")
    return None


def tcgdex_card_prices(row, usd_eur, need_cardmarket=True):
    """Recherche + prix en un appel. Retourne (card, prices) ou (None, {})."""
    card = find_card_tcgdex(row)
    if not card:
        return None, {}
    listing_id = card["id"]
    detail = tcgdex_get(TCGDEX_URL + "/" + urllib.parse.quote(str(listing_id)))
    pricing = (detail or {}).get("pricing") or {}
    if need_cardmarket and not pricing.get("cardmarket"):
        print(f"TCGdex : pas de prix Cardmarket pour {listing_id} en anglais, essai en français")
        for alt_url in (
            TCGDEX_URL.replace("/en/", "/fr/") + "/" + urllib.parse.quote(str(listing_id)),
            TCGDEX_URL + "/" + urllib.parse.quote(str(listing_id)) + f"?nocache={int(time.time())}",
        ):
            alt_pricing = (tcgdex_get(alt_url) or {}).get("pricing") or {}
            if alt_pricing.get("cardmarket"):
                pricing = alt_pricing
                break
        else:
            print(f"TCGdex : toujours aucun prix Cardmarket pour {listing_id}. Reçu : {json.dumps((detail or {}).get('pricing'))[:300]}")
    prices = {}
    cm = pricing.get("cardmarket") or {}
    if cm.get("unit", "EUR") == "EUR":
        trend = cm.get("trend-holo") or cm.get("trend")
        avg30 = cm.get("avg30-holo") or cm.get("avg30")
        avg7 = cm.get("avg7-holo") or cm.get("avg7")
        if avg7:
            prices["Cardmarket moyenne 7 j"] = float(avg7)
        if trend:
            prices["Cardmarket tendance"] = float(trend)
        if avg30:
            prices["Cardmarket moyenne 30 j"] = float(avg30)
    tp = pricing.get("tcgplayer") or {}
    if usd_eur:
        for variant, data in tp.items():
            if isinstance(data, dict) and data.get("marketPrice"):
                prices[f"TCGplayer {variant} (converti)"] = float(data["marketPrice"]) * usd_eur
    return card, prices


# ---------- PokemonPriceTracker (PSA 10 + prix de secours) ----------
def ppt_get(params):
    url = PPT_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {PPT_KEY}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp).get("data")
                if isinstance(data, dict):  # l'API renvoie parfois un objet seul plutôt qu'une liste
                    data = [data]
                return data or []
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
    if not data:
        return {}, None
    return (data[0] if isinstance(data, list) else data), None


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
    """Prix utilisé pour les prix cibles : Cardmarket moyenne 7 j, sinon tendance, sinon TCGplayer converti."""
    if "Cardmarket moyenne 7 j" in prices:
        return "Cardmarket moyenne 7 j", prices["Cardmarket moyenne 7 j"]
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
    guide_date, _ = cardmarket.load_price_guide()

    with CARDS_FILE.open(newline="", encoding="utf-8") as f:
        cards = [r for r in csv.DictReader(f) if (r.get("nom") or "").strip()]

    history_rows, alerts, blocks, problems = [], [], [], []
    new_summary = {}

    for row in cards:
        label = row["nom"].strip()
        fallback_note = None

        # Source principale : guide des prix Cardmarket (fichier officiel, quotidien, gratuit)
        cm_prices = cardmarket.product_prices(row.get("cardmarket_id"))
        if row.get("cardmarket_id") and not cm_prices:
            print(f"Guide Cardmarket : pas de prix pour {label} (produit {row.get('cardmarket_id')})")

        # TCGdex : fiche de la carte et prix TCGplayer (et Cardmarket si le guide n'a rien)
        card, prices = tcgdex_card_prices(row, usd_eur, need_cardmarket=not cm_prices)
        if cm_prices:
            prices = {k: v for k, v in prices.items() if not k.startswith("Cardmarket")}
            prices.update(cm_prices)
            card = card or minimal_card(row)
            card["cardmarket"] = {**(card.get("cardmarket") or {}), "updatedAt": guide_date or today}

        # Secours 1 : API Pokémon TCG (en fin de vie, gardée tant qu'elle répond)
        if not card or not prices:
            alt_card = fetch_card(row)
            if alt_card:
                card = card or alt_card
                alt_prices = extract_prices_eur(alt_card, usd_eur)
                if alt_prices and not prices:
                    prices = alt_prices
                    card = alt_card
                    fallback_note = "ℹ️ Prix issus de l'API Pokémon TCG (en fin de vie, TCGdex n'avait pas encore de prix)."

        if not card:
            problems.append(f"⚠️ {label} : carte introuvable sur les sources disponibles")
            continue
        card_id = card["id"]

        # Secours 2 : PokemonPriceTracker (prix TCGplayer, nécessite une clé)
        if not prices:
            try:
                prices = ppt_market_prices(state, card, card_id, usd_eur)
                if prices:
                    fallback_note = "ℹ️ Prix TCGplayer issus de PokemonPriceTracker (les autres sources n'ont pas encore de prix)."
            except Exception as exc:
                print(f"PokemonPriceTracker (prix) : erreur inattendue ignorée : {exc}")
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
            try:
                lines.append(get_psa10_line(state, card, card_id, usd_eur))
            except Exception as exc:
                print(f"PSA 10 : erreur inattendue ignorée : {exc}")
                lines.append(" • PSA 10 : indisponible aujourd'hui (erreur inattendue)")
            lines.append(f" 🔗 Ventes eBay PSA 10 : {ebay_psa10_link(card)}")
        if fallback_note:
            lines.append(f" {fallback_note}")
        blocks.append(f"{label}\n" + "\n".join(lines))
        new_summary[card_id] = prices
        time.sleep(1)

    # Historique complet (un fichier CSV) : on remplace les lignes du jour si le script
    # a déjà tourné aujourd'hui, pour ne pas les dupliquer
    old_rows = []
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open(newline="", encoding="utf-8") as f:
            old_rows = list(csv.reader(f))[1:]
    done_today = {r[1] for r in history_rows}
    old_rows = [r for r in old_rows if not (r and r[0] == today and r[1] in done_today)]
    with HISTORY_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "card_id", "name", "source", "price_eur"])
        writer.writerows(old_rows + history_rows)

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
