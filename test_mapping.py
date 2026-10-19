"""Test de correspondance carte → bonne version sur Cardmarket.

Pour chaque carte de cards.csv :
  1. on trouve la carte sur TCGdex (même méthode que la veille : nom anglais + numéro + set) ;
  2. on regarde si TCGdex donne l'identifiant produit Cardmarket (idProduct) ;
  3. on retrouve ce produit dans les fichiers officiels Cardmarket et on compare les prix.
On cherche aussi comment Cardmarket nomme quelques produits scellés.
Résultat dans test_mapping_report.md.
"""
import csv
import json
import time
import urllib.parse

import track  # réutilise la recherche TCGdex de la veille

CM = "https://downloads.s3.cardmarket.com/productCatalog"
TCGDEX = "https://api.tcgdex.net/v2"
out = []


def say(line=""):
    print(line)
    out.append(line)


def items(data):
    for v in (data or {}).values():
        if isinstance(v, list):
            return v
    return []


say("# Correspondance cartes → Cardmarket")
say(f"_Lancé le {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_")
say()

guide = {e["idProduct"]: e for e in items(track.tcgdex_get(f"{CM}/priceGuide/price_guide_6.json"))}
singles = items(track.tcgdex_get(f"{CM}/productList/products_singles_6.json"))
sealed = items(track.tcgdex_get(f"{CM}/productList/products_nonsingles_6.json"))
catalog = {p["idProduct"]: p for p in singles + sealed}
say(f"Fichiers Cardmarket chargés : {len(guide)} prix, {len(singles)} cartes, {len(sealed)} scellés.")
say()

ok = 0
rows = list(csv.DictReader(open("cards.csv", encoding="utf-8")))
for row in rows:
    say(f"## {row['nom']}")
    card = track.find_card_tcgdex(row)
    if not card:
        say("- ❌ Carte introuvable sur TCGdex")
        continue
    detail = track.tcgdex_get(f"{TCGDEX}/en/cards/{urllib.parse.quote(card['id'])}") or {}
    fr = track.tcgdex_get(f"{TCGDEX}/fr/cards/{urllib.parse.quote(card['id'])}") or {}
    say(f"- TCGdex : `{card['id']}` · {detail.get('name')} {detail.get('localId')} · {(detail.get('set') or {}).get('name')} · nom français : **{fr.get('name') or 'non traduit'}**")
    cm = (detail.get("pricing") or {}).get("cardmarket") or {}
    say(f"- Bloc Cardmarket chez TCGdex : `{json.dumps(cm, ensure_ascii=False)[:400]}`")
    pid = cm.get("idProduct") or cm.get("productId") or cm.get("id")
    if not pid:
        say("- ❌ TCGdex ne donne pas d'identifiant produit Cardmarket pour cette carte")
        continue
    prod, price = catalog.get(int(pid)), guide.get(int(pid))
    if not prod:
        say(f"- ❌ idProduct {pid} absent du catalogue Cardmarket")
        continue
    ok += 1
    say(f"- ✅ Produit Cardmarket **{pid}** : {prod.get('name')} (extension {prod.get('idExpansion')})")
    if price:
        keep = {k: price[k] for k in ("trend", "avg", "low", "avg7", "avg30", "trend-holo", "avg30-holo") if price.get(k)}
        say(f"- Cote du fichier officiel : `{json.dumps(keep)}`")
        if cm.get("trend") or cm.get("trend-holo"):
            say(f"- Contrôle : tendance TCGdex {cm.get('trend')} / holo {cm.get('trend-holo')} · fichier officiel {price.get('trend')} / holo {price.get('trend-holo')}")
    same = [p for p in singles if p.get("idExpansion") == prod.get("idExpansion") and p.get("name") == prod.get("name")]
    if len(same) > 1:
        say(f"- ℹ️ {len(same)} versions portent exactement ce nom dans cette extension : sans l'identifiant, impossible de choisir la bonne")
    say()

say(f"**Bilan : {ok} carte(s) sur {len(rows)} reliées à la bonne version Cardmarket.**")
say()
say("## Noms des produits scellés chez Cardmarket")
for words in (["Obsidian Flames"], ["151", "Ultra"], ["151", "Elite Trainer"], ["Surging Sparks", "Booster"], ["Journey Together"]):
    hits = [p for p in sealed if all(w.lower() in p.get("name", "").lower() for w in words)]
    say(f"- {' + '.join(words)} : {len(hits)} produit(s)")
    for p in hits[:6]:
        pr = guide.get(p["idProduct"], {})
        say(f"  - {p['name']} (id {p['idProduct']}) · tendance {pr.get('trend')} €")

open("test_mapping_report.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
