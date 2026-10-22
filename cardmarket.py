"""Guide des prix Cardmarket : fichier public et gratuit que Cardmarket publie chaque jour.

Il contient, pour chaque produit Pokémon (identifié par son idProduct Cardmarket) :
avg (prix de vente moyen, celui qu'affiche PokéCardex), low, trend, avg1, avg7, avg30,
et les mêmes champs suffixés « -holo » pour les versions reverse.

Un seul téléchargement par passage, partagé par track.py et pokedex.py.
"""
import json
import time
import urllib.request
from pathlib import Path

PRICE_GUIDE_URL = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"  # 6 = Pokémon
CACHE_FILE = Path("price_guide_6.json")  # copie locale, jamais enregistrée dans le dépôt
CACHE_MAX_AGE = 6 * 3600  # secondes

_guide = None


def _download():
    req = urllib.request.Request(PRICE_GUIDE_URL, headers={"User-Agent": "Mozilla/5.0 (pokemon-watch)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            data = json.loads(raw)
            CACHE_FILE.write_bytes(raw)
            return data
        except Exception as exc:
            print(f"Guide des prix Cardmarket : tentative {attempt + 1} échouée : {exc}")
            time.sleep(5 * (attempt + 1))
    return None


def load_price_guide():
    """Retourne (date du fichier, {idProduct: ligne de prix}). (None, {}) si indisponible."""
    global _guide
    if _guide is not None:
        return _guide
    data = None
    if CACHE_FILE.exists() and time.time() - CACHE_FILE.stat().st_mtime < CACHE_MAX_AGE:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            data = None
    if data is None:
        data = _download()
    if not data:
        print("Guide des prix Cardmarket indisponible aujourd'hui")
        _guide = (None, {})
        return _guide

    rows = data.get("priceGuides") if isinstance(data, dict) else data
    if rows is None and isinstance(data, dict):
        rows = next((v for v in data.values() if isinstance(v, list)), [])
    guide = {}
    for row in rows or []:
        try:
            guide[int(row["idProduct"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    created = None
    if isinstance(data, dict):
        created = str(data.get("createdAt") or "")[:10] or None
    print(f"Guide des prix Cardmarket : {len(guide)} produits (fichier du {created})")
    _guide = (created, guide)
    return _guide


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def product_row(id_product):
    """Ligne brute du guide pour un produit, ou None."""
    try:
        id_product = int(str(id_product).strip())
    except (TypeError, ValueError):
        return None
    return load_price_guide()[1].get(id_product)


def field(row, name):
    """Un champ de prix ; si le champ normal est vide, essaie la version « -holo »."""
    if not row:
        return None
    value = _num(row.get(name))
    if value is None:
        value = _num(row.get(f"{name}-holo"))
    return value


def product_prices(id_product):
    """Prix Cardmarket d'un produit, avec les libellés utilisés dans history.csv."""
    row = product_row(id_product)
    prices = {}
    for name, label in (
        ("avg7", "Cardmarket moyenne 7 j"),
        ("trend", "Cardmarket tendance"),
        ("avg30", "Cardmarket moyenne 30 j"),
    ):
        value = field(row, name)
        if value is not None:
            prices[label] = value
    return prices


def average_sell_price(id_product):
    """Prix de vente moyen (champ avg), comme sur PokéCardex ; sinon tendance, sinon moyenne 7 j."""
    row = product_row(id_product)
    for name in ("avg", "trend", "avg7", "avg30"):
        value = field(row, name)
        if value is not None:
            return value
    return None
