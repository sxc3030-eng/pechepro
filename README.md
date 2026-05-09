# pechepro

App Windows **standalone** gratuite de pêche en Amérique du Nord avec recommandations personnalisées par espèce, région et conditions (météo, pression baro, lune, soleil, solunar).

**Status :** Spec v0.1 (v3 — pivot architecture pure desktop, zéro backend) — implémentation à venir
**Spec design :** [docs/superpowers/specs/2026-05-09-pechepro-design.md](docs/superpowers/specs/2026-05-09-pechepro-design.md)
**Distribution :** `.exe` Windows installable directement, aucun service à déployer

## Architecture rapide

App auto-suffisante :
- **PyWebView shell** + **Flask local** (port dynamique 127.0.0.1) + **SQLite locale** (`%LOCALAPPDATA%\pechepro\pechepro.db`)
- **Services in-process** : recommender, solunar, baro_analyzer, astral (soleil/lune), openmeteo client, usgs/eccc water-temp clients, data_sync depuis GitHub raw
- **Données curées** bundlées au build + sync 1×/24h depuis `raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/*.csv`
- **APIs externes** appelées directement par l'app (no proxy, no backend) : Open-Meteo (météo + baro), USGS Water Data (US), ECCC (Canada)
- **Monétisation** widget Expedia Affiliate Banners leaderboard 728×90 (camref `1101l5IQud`, pubref `pechepro-tips`)

**Zéro infra :** pas de cloud, pas de VPS, pas de tunnel, pas de DB hébergée. Master livre le `.exe` et oublie.

## Espèces MVP (15)

Achigan G/B + P/B · Doré jaune + noir · Brochet · Maskinongé · Truite mouchetée + arc-en-ciel + brune · Touladi · Saumon atlantique · Ouananiche · Perchaude · Crapet-soleil · Barbue de rivière

## Structure

```
app/                  Tout le code applicatif Python
  ├─ shell.py        Entry point PyWebView (le .exe lance ça)
  ├─ server.py       Flask local
  ├─ services/       recommender, solunar, baro, astral, openmeteo, usgs, eccc, data_sync, geolocation
  ├─ db/             schema.sql, migrations, seed_initial.sql
  ├─ templates/      Jinja2 (home, conditions, tips)
  └─ static/         CSS, JS, images leurres + icons

data/curated/        CSVs sources de vérité (species, regions, lures, tips, color_visibility, solunar_rules, baro_rules)
                     Bundlés dans le .exe + servis via GitHub raw pour mises à jour live

deploy/windows/      build.ps1 + installer.iss (Inno Setup) + sign.ps1
.github/workflows/   release.yml (build .exe sur tag v*)
docs/                Specs + plans superpowers
tests/               pytest (services + Flask routes + smoke E2E)
```
