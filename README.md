# pechepro

App Windows gratuite de pêche en Amérique du Nord avec recommandations personnalisées par espèce, région et conditions (météo, pression baro, lune, soleil, solunar).

**Status :** Spec v0.1 — implémentation à venir
**Spec design :** [docs/superpowers/specs/2026-05-09-pechepro-design.md](docs/superpowers/specs/2026-05-09-pechepro-design.md)

## Architecture rapide

- **Backend** Python FastAPI + SQLite hébergé sur i5 via Cloudflare tunnel (API publique gratuite)
- **App Windows** Python + PyWebView, .exe signé Inno Setup, offline-capable
- **Données** curées manuellement (15 espèces NA prioritaires) + APIs gratuites (Open-Meteo, USGS, ECCC)
- **Monétisation** bannière Expedia (freemium ad-supported)

## Espèces MVP (15)

Achigan G/B + P/B · Doré jaune + noir · Brochet · Maskinongé · Truite mouchetée + arc-en-ciel + brune · Touladi · Saumon atlantique · Ouananiche · Perchaude · Crapet-soleil · Barbue de rivière

## Structure

```
backend/        FastAPI + SQLite + services solunar/baro/recommender
frontend/       PyWebView + Flask local + HTML/CSS/JS + cache offline
data/curated/   CSVs sources de vérité (species, regions, lures, tips, color_visibility)
deploy/i5/      Scripts setup i5 + cloudflared
deploy/windows/ Inno Setup + PyInstaller build
docs/           Specs + plans superpowers
```
