# Test des sources de prix
_Lancé le 2026-10-19 14:14 UTC_

## 1. Cardmarket, fichiers officiels gratuits
- Jeu Pokémon trouvé : numéro **6** (catalogue des cartes, 13.7 Mo)
- `https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_6.json` → OK, 0.9 Mo
- `https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json` → OK, 15.7 Mo
- Cote : **79782 produits**. Champs disponibles : `avg, avg-holo, avg1, avg1-holo, avg30, avg30-holo, avg7, avg7-holo, idCategory, idProduct, low, low-holo, trend, trend-holo`
- En-tête du fichier : `{"version": 1, "createdAt": "2026-10-19T02:42:46+0200"}`
- Catalogue : 74717 cartes, 5076 produits scellés. Champs : `categoryName, dateAdded, idCategory, idExpansion, idMetacard, idProduct, name`

**Carte : Gengar ex (Ectoplasma ex)**
- Gengar ex [Poltergeist | Prize Count] (id 276284, extension 1544) → `{"idCategory": 51, "avg": 807, "low": 99, "trend": 793, "avg1": 782.67, "avg7": 983.23, "avg30": 777.9, "trend-holo": 54.86, "avg1-holo": 69.99, "avg7-holo": 60.55, "avg30-holo": 35.45}`
- Gengar EX [Night Attack | Dark Corridor] (id 281840, extension 1521) → `{"idCategory": 51, "avg": 54.02, "low": 9.98, "trend": 339.37, "avg1": 29.49, "avg7": 175.52, "avg30": 92.51, "trend-holo": 7.21, "avg1-holo": 9.28, "avg7-holo": 7.92, "avg30-holo": 7.83}`
- MGengar EX [Phantom Gate] (id 281841, extension 1521) → `{"idCategory": 51, "avg": 100.99, "low": 17, "trend": 139.44, "avg1": 159.99, "avg7": 122.14, "avg30": 116.27, "trend-holo": 16.11, "avg1-holo": 25, "avg7-holo": 15.71, "avg30-holo": 12.58}`
- Gengar EX [Night Attack | Dark Corridor] (id 281921, extension 1521) → `{"idCategory": 51, "avg": 548.75, "low": 120, "trend": 689.69, "avg1": 1366.66, "avg7": 804.5, "avg30": 520.76, "trend-holo": 59.04, "avg1-holo": 54.99, "avg7-holo": 64.27, "avg30-holo": 30.94}`
- … et 41 autres résultats

**Carte : Mega Darkrai ex**
- Mega Darkrai ex [Dusk Raid | Abyss Eye] (id 888301, extension 6556) → `{"idCategory": 51, "avg": 0.5, "low": 0.15, "trend": 0.51, "avg1": 0.5, "avg7": 0.59, "avg30": 0.51}`
- Mega Darkrai ex [Dusk Raid | Abyss Eye] (id 888644, extension 6556) → `{"idCategory": 51, "avg": 7.07, "low": 4, "trend": 5.28, "avg1": 4.25, "avg7": 5.46, "avg30": 6.21}`
- Mega Darkrai ex [Dusk Raid | Abyss Eye] (id 888659, extension 6556) → `{"idCategory": 51, "avg": 171.59, "low": 105, "trend": 110.24, "avg1": 123.6, "avg7": 116.96, "avg30": 154.99}`
- Mega Darkrai ex [Dusk Raid | Abyss Eye] (id 888663, extension 6556) → `{"idCategory": 51, "avg": 255.92, "low": 139.99, "trend": 148.52, "avg1": 240, "avg7": 242.99, "avg30": 378.45}`
- … et 10 autres résultats

**Scellé : Elite Trainer Box Prismatic Evolutions**
- Prismatic Evolutions Elite Trainer Box (id 798930, extension 5944) → `{"idCategory": 1016, "avg": 151.23, "low": 85, "trend": 149.83}`
- Prismatic Evolutions Pokémon Center Elite Trainer Box (id 798931, extension 5944) → `{"idCategory": 1016, "avg": 479.79, "low": 430, "trend": 475.6}`
- Prismatic Evolutions 10 Elite Trainer Box Case (id 798932, extension 5944) → `{"idCategory": 1016, "avg": 1704.29, "low": 1000, "trend": 1592.54}`

**Scellé : Booster Display Obsidian Flames**
- aucun produit dont le nom contient ['Obsidian Flames', 'Display']

**Scellé : Ultra Premium Collection 151**
- aucun produit dont le nom contient ['Ultra Premium', '151']

## 2. Poké Price Tracker (clé gratuite déjà dans les secrets)
- `cards?tcgPlayerId=717610&includeEbay=true` → OK
  - Carte : Gengar ex - 154/128 154/128 · ME: 30th Celebration
  - Champs de la fiche : `artist, attacks, cardNumber, cardType, createdAt, dataCompleteness, ebay, energyType, externalCatalogId, flavorText, hp, id, imageCdnUrl, imageCdnUrl200, imageCdnUrl400, imageCdnUrl800, imageUrl, lastScrapedAt, name, needsDetailedScrape, pokedexNumbers, pokemonType, prices, printingsAvailable, rarity, resistance, retreatCost, setId, setName, stage, tcgPlayerId, tcgPlayerUrl, totalSetNumber, updatedAt, variants, weakness`
  - Prix : `{"market": 75.75, "low": 65, "sellers": 154, "listings": 170, "recentSales": 0, "primaryPrinting": "Holofoil", "lastUpdated": "2026-10-19T12:01:01.723Z", "variants": {"Holofoil": {"Near Mint Holofoil": {"price": 75.75, "listings": null, "priceString": "$75.75", "lastUpdated": "2026-10-19T12:01:01.723Z"}}}}`
  - Ventes eBay par note : `ace10 (19 ventes), cgc10 (24 ventes), psa10 (14 ventes), tag10 (6 ventes), ace8 (1 ventes), cgc8_5 (1 ventes), bgs10 (1 ventes), cgc9_5 (2 ventes), cgc9 (1 ventes), psa9 (2 ventes)`
  - Champ européen `imageUrl` : `"https://tcgplayer-cdn.tcgplayer.com/product/717610_in_200x200.jpg"`
  - Crédits / quota : `{"total": 1, "count": 1, "limit": 1, "offset": 0, "hasMore": false, "language": "english", "includes": {"priceHistory": false, "ebayData": true, "cardmarketData": false}, "historyWindow": {"days": 3, "from": "2026-10-16", "to": "2026-10-19", "maxDataPoints": 30, "granularityNote": "Data points limit`
- `sealed-products?search=Prismatic+Evolutions+Elite+Trainer+Box&limit=3` → OK
  - Prismatic Evolutions Elite Trainer Box and Pokeball (Sam's Club) → prix `{"unopenedPrice": 189.44}`
  - Prismatic Evolutions Elite Trainer Box Case → prix `{"unopenedPrice": 1278.3}`
  - Prismatic Evolutions Elite Trainer Box (Dollar General Exclusive) → prix `{"unopenedPrice": 198.83}`
