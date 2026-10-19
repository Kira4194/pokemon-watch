"""Test des sources de prix pour le futur bot Cotéo.

Vérifie, sans rien modifier dans la veille quotidienne :
  1. Cardmarket : le fichier officiel de cote (Price Guide) et le catalogue produits
     (cartes + produits scellés), téléchargeables gratuitement.
  2. Poké Price Tracker : une carte (prix + ventes eBay par note PSA/CGC/BGS)
     et un produit scellé.
Le résultat est écrit dans test_sources_report.md.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PPT_KEY = os.environ.get("POKEPRICETRACKER_API_KEY", "")
CM_BASE = "https://downloads.s3.cardmarket.com/productCatalog"
UA = {"User-Agent": "coteo-source-test/1.0"}
out = []


def say(line=""):
    print(line)
    out.append(line)


def get(url, headers=None, timeout=120):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:500]
    except Exception as exc:  # réseau, délai…
        return None, str(exc).encode()


def load_json(url):
    status, body = get(url)
    if status != 200:
        say(f"- `{url}` → **échec** (statut {status}) : {body[:200]!r}")
        return None
    data = json.loads(body)
    say(f"- `{url}` → OK, {len(body) / 1e6:.1f} Mo")
    return data


def entries(data):
    """Les fichiers Cardmarket contiennent une liste sous une clé (priceGuides, products…)."""
    if isinstance(data, list):
        return data
    for v in (data or {}).values():
        if isinstance(v, list):
            return v
    return []


# ---------------------------------------------------------------- Cardmarket
say("# Test des sources de prix")
say(f"_Lancé le {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_")
say()
say("## 1. Cardmarket, fichiers officiels gratuits")

game = None
guide = singles = sealed = None
for gid in (6, 3, 1, 2, 4, 5, 7, 8, 9, 10, 11, 12):  # on cherche le numéro de jeu du Pokémon
    st, body = get(f"{CM_BASE}/productList/products_singles_{gid}.json")
    if st == 200 and b"Pikachu" in body and b"Charizard" in body:
        game = gid
        singles = json.loads(body)
        say(f"- Jeu Pokémon trouvé : numéro **{gid}** (catalogue des cartes, {len(body) / 1e6:.1f} Mo)")
        break
if game is None:
    say("- **Catalogue Pokémon introuvable** aux adresses testées.")
else:
    sealed = load_json(f"{CM_BASE}/productList/products_nonsingles_{game}.json")
    guide = load_json(f"{CM_BASE}/priceGuide/price_guide_{game}.json")

if guide:
    g = entries(guide)
    say(f"- Cote : **{len(g)} produits**. Champs disponibles : `{', '.join(sorted(g[0].keys()))}`")
    meta = {k: v for k, v in guide.items() if not isinstance(v, list)} if isinstance(guide, dict) else {}
    if meta:
        say(f"- En-tête du fichier : `{json.dumps(meta, ensure_ascii=False)[:300]}`")
    by_id = {e.get("idProduct"): e for e in g}
    sp = entries(singles)
    ns = entries(sealed)
    say(f"- Catalogue : {len(sp)} cartes, {len(ns)} produits scellés. Champs : `{', '.join(sorted(sp[0].keys()))}`")

    def show(label, items, words, limit=4):
        say(f"\n**{label}**")
        hits = [p for p in items if all(w.lower() in str(p.get("name", "")).lower() for w in words)]
        if not hits:
            say(f"- aucun produit dont le nom contient {words}")
            return
        for p in hits[:limit]:
            price = by_id.get(p.get("idProduct"), {})
            keep = {k: v for k, v in price.items() if k != "idProduct" and v not in (None, 0, 0.0)}
            say(f"- {p.get('name')} (id {p.get('idProduct')}, extension {p.get('idExpansion')}) → `{json.dumps(keep, ensure_ascii=False)}`")
        if len(hits) > limit:
            say(f"- … et {len(hits) - limit} autres résultats")

    show("Carte : Gengar ex (Ectoplasma ex)", sp, ["Gengar ex"])
    show("Carte : Mega Darkrai ex", sp, ["Mega Darkrai ex"])
    show("Scellé : Elite Trainer Box Prismatic Evolutions", ns, ["Elite Trainer Box", "Prismatic"])
    show("Scellé : Booster Display Obsidian Flames", ns, ["Obsidian Flames", "Display"])
    show("Scellé : Ultra Premium Collection 151", ns, ["Ultra Premium", "151"])

# ------------------------------------------------------- Poké Price Tracker
say()
say("## 2. Poké Price Tracker (clé gratuite déjà dans les secrets)")
PPT = "https://www.pokemonpricetracker.com/api/v2"


def ppt(path, params):
    if not PPT_KEY:
        say(f"- `{path}` : pas de clé disponible dans ce lancement")
        return None
    url = f"{PPT}/{path}?{urllib.parse.urlencode(params)}"
    st, body = get(url, {"Authorization": f"Bearer {PPT_KEY}"}, timeout=60)
    shown = urllib.parse.urlencode(params)
    if st != 200:
        say(f"- `{path}?{shown}` → **statut {st}** : {body[:200]!r}")
        return None
    data = json.loads(body)
    say(f"- `{path}?{shown}` → OK")
    return data


card = ppt("cards", {"tcgPlayerId": "717610", "includeEbay": "true"})  # Ectoplasma ex 154/128
if card:
    d = card.get("data")
    d = d[0] if isinstance(d, list) and d else d
    if isinstance(d, dict):
        say(f"  - Carte : {d.get('name')} {d.get('cardNumber')} · {d.get('setName')}")
        say(f"  - Champs de la fiche : `{', '.join(sorted(d.keys()))}`")
        say(f"  - Prix : `{json.dumps(d.get('prices'), ensure_ascii=False)[:400]}`")
        grades = ((d.get("ebay") or {}).get("salesByGrade") or {})
        say(f"  - Ventes eBay par note : `{', '.join(f'{k} ({(v or {}).get('count', 0)} ventes)' for k, v in grades.items()) or 'aucune'}`")
        for k in [k for k in d.keys() if "cardmarket" in k.lower() or "eur" in k.lower()]:
            say(f"  - Champ européen `{k}` : `{json.dumps(d[k], ensure_ascii=False)[:200]}`")
    if isinstance(card, dict) and card.get("metadata"):
        say(f"  - Crédits / quota : `{json.dumps(card['metadata'], ensure_ascii=False)[:300]}`")

for path, params in (
    ("sealed-products", {"search": "Prismatic Evolutions Elite Trainer Box", "limit": 3}),
    ("sealed", {"search": "Prismatic Evolutions Elite Trainer Box", "limit": 3}),
):
    res = ppt(path, params)
    if res:
        items = res.get("data") or []
        items = items if isinstance(items, list) else [items]
        for it in items[:3]:
            say(f"  - {it.get('name')} → prix `{json.dumps(it.get('prices') or {k: it[k] for k in it if 'price' in k.lower()}, ensure_ascii=False)[:300]}`")
        break

with open("test_sources_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("\nRapport écrit dans test_sources_report.md")
