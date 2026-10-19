"""Plan B : quand TCGdex ne donne pas l'identifiant Cardmarket, on propose les versions possibles.

1. On retrouve l'extension Cardmarket qui contient toutes les cartes du même set
   (ici Gengar ex, Mew ex et Sylveon ex), en préférant la plus récente.
2. Pour chaque carte, on liste les versions de ce nom dans l'extension, avec leur cote.
3. On suggère la version dont le prix est le plus proche du prix TCGplayer connu
   (converti en euros), sans jamais choisir à la place de l'utilisateur.
Résultat dans test_planb_report.md.
"""
import json
import time
from collections import defaultdict

import track

CM = "https://downloads.s3.cardmarket.com/productCatalog"
out = []


def say(line=""):
    print(line)
    out.append(line)


def items(data):
    for v in (data or {}).values():
        if isinstance(v, list):
            return v
    return []


say("# Plan B : choix de la version Cardmarket")
say(f"_Lancé le {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_")
say()

guide = {e["idProduct"]: e for e in items(track.tcgdex_get(f"{CM}/priceGuide/price_guide_6.json"))}
singles = items(track.tcgdex_get(f"{CM}/productList/products_singles_6.json"))
usd_eur = track.get_usd_eur_rate() or 0.92
state = json.load(open("state.json", encoding="utf-8"))

CARDS = [  # (nom affiché, nom anglais Cardmarket, id de la veille)
    ("Ectoplasma ex 154/128", "Gengar ex", "30th-154"),
    ("Nymphali ex 153/128", "Sylveon ex", "30th-153"),
    ("Mew ex 152/128", "Mew ex", "30th-152"),
    ("Mew ex 158/128", "Mew ex", "30th-158"),
]
names = {c[1] for c in CARDS}

# 1. Extension qui contient tous ces noms
by_exp = defaultdict(list)
for p in singles:
    base = p.get("name", "").split(" [")[0]
    if base in names:
        by_exp[p["idExpansion"]].append(p)
cands = [(e, ps) for e, ps in by_exp.items() if {p["name"].split(" [")[0] for p in ps} >= names]
cands.sort(key=lambda x: max(p.get("dateAdded", "") for p in x[1]), reverse=True)
say(f"Extensions contenant à la fois {', '.join(sorted(names))} : **{len(cands)}**")
for e, ps in cands[:4]:
    say(f"- extension {e} · {len(ps)} produits · ajoutés le {min(p.get('dateAdded', '')[:10] for p in ps)}")
if not cands:
    say("❌ Aucune extension commune trouvée.")
else:
    exp, prods = cands[0]
    say(f"\n➡️ Extension retenue : **{exp}** (la plus récente)\n")
    for label, en, sid in CARDS:
        ref_usd = (state.get("summary", {}).get(sid) or {}).get("TCGplayer (via PokemonPriceTracker, converti)")
        ref = ref_usd  # déjà converti en euros par la veille
        versions = sorted([p for p in prods if p["name"].split(" [")[0] == en], key=lambda p: p["idProduct"])
        say(f"## {label}")
        say(f"Prix de référence TCGplayer (converti) : {track.fmt_eur(ref) if ref else 'inconnu'} · {len(versions)} version(s) proposée(s) :")
        best = None
        if ref:
            priced = [v for v in versions if guide.get(v["idProduct"], {}).get("trend")]
            if priced:
                best = min(priced, key=lambda v: abs(guide[v["idProduct"]]["trend"] - ref))["idProduct"]
        for i, v in enumerate(versions, 1):
            g = guide.get(v["idProduct"], {})
            tag = " ← **suggérée**" if v["idProduct"] == best else ""
            say(f"{i}. id {v['idProduct']} · {v['name']} · tendance {g.get('trend')} € · moy. 30 j {g.get('avg30')} € · bas {g.get('low')} €{tag}")
        say()

open("test_planb_report.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
