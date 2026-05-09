# pechepro — Design Spec v0.1

**Date :** 2026-05-09
**Auteur :** bul4 + Master
**Status :** Draft, en attente d'approbation
**Repo :** `D:\pechepro\`

## 1. Problème et objectifs

Les pêcheurs nord-américains manquent d'une app **personnalisée et contextuelle** qui combine en un seul endroit : conditions météo locales, pression barométrique, phases de lune (solunar major/minor), lever/coucher de soleil, et **astuces ciblées par espèce × région × conditions** (couleurs de leurres selon turbidité, profondeur, présentation, structure).

Apps existantes : génériques (météo seule), payantes (Fishbrain), ou trop techniques (Solunar Pro). Aucune ne donne des recommandations actionnables en français pour le marché québécois et nord-américain.

**Objectif v0.1 :** App Windows gratuite (revenu pub Expedia), backend public gratuit (DB hébergée sur i5 via Cloudflare tunnel), 15 espèces NA prioritaires, FR + EN, offline-capable.

**Critères de succès :**
- App lance en moins de 3 sec, recommandation en moins de 2 sec
- Fonctionne sans internet (DB clonée localement, météo cachée 7 jours)
- Astuces traçables (chaque tip a une source citée)
- Build distribuable .exe + installer Inno Setup, app <60 MB (PyWebView + Python embedded)
- API publique read-only sans clé pour usage tiers

## 2. Architecture

```
┌──────────────────────────┐         ┌─────────────────────┐
│  App Windows (.exe)      │ HTTPS   │  Cloudflare tunnel  │
│  Python + PyWebView      │────────▶│  pechepro.<domain>  │
│  - HTML/CSS/JS local     │         └──────────┬──────────┘
│  - SQLite cache local    │                    │
│  - Bannière Expedia      │                    ▼
└──────────────────────────┘         ┌─────────────────────┐
                                     │  Backend i5         │
                                     │  FastAPI + SQLite   │
                                     │  + cloudflared svc  │
                                     └─────────────────────┘
                                                │
                                                ▼
                                     ┌─────────────────────┐
                                     │  APIs externes      │
                                     │  - Open-Meteo       │
                                     │  - USGS Water Data  │
                                     │  - ECCC (Canada)    │
                                     └─────────────────────┘
```

**Pourquoi cette architecture :**
- **Backend séparé** : la base de connaissances peut servir d'autres apps plus tard (mobile, web, plugin Slack, etc.)
- **API publique gratuite** : Master peut publier l'endpoint comme service communautaire (différenciateur)
- **App offline-first** : cache local + soleil/lune calculés localement (lib `astral`) → utilisable sur lac sans réseau
- **i5 hébergé** : pas de coût cloud récurrent, contrôle total des données curées

## 3. Composants

### 3.1 Backend (`backend/`)

**Stack :** Python 3.13 · FastAPI · SQLite · uvicorn · pydantic v2

**Modules :**
- `app/main.py` — FastAPI bootstrap + CORS + middleware logging
- `app/db/schema.sql` — DDL des 8 tables (voir §4)
- `app/db/seed.py` — chargement des CSV curés depuis `data/curated/`
- `app/routes/species.py` — `GET /v1/species`, `GET /v1/species/{id}`
- `app/routes/regions.py` — `GET /v1/regions`, `GET /v1/water-types`
- `app/routes/astro.py` — `GET /v1/sun-moon?lat=&lon=&date=` (calculé via `astral` + `skyfield`)
- `app/routes/weather.py` — `GET /v1/weather?lat=&lon=` (proxy Open-Meteo, cache 30 min)
- `app/routes/recommend.py` — `POST /v1/recommend` (orchestrateur principal)
- `app/routes/health.py` — `GET /v1/health` (uptime + DB connectivity)
- `app/services/solunar.py` — algorithme major/minor periods (lune transit ± 1h, opposite ± 1h)
- `app/services/baro_analyzer.py` — tendance baro 6h/24h + score activité par espèce
- `app/services/recommender.py` — query DB tips + ranking par match conditions
- `app/services/openmeteo_client.py` — wrapper requests Open-Meteo
- `tests/` — pytest, ≥80% coverage cible

**Interface publique :** REST JSON, OpenAPI auto-généré (`/docs`), versionné `/v1/`.

**Dépendances :** Open-Meteo (no key, attribution), USGS Water Data (no key, US only), ECCC (Canada, public). `astral` 3.x, `skyfield` 1.x, `httpx`, `fastapi`, `uvicorn`, `pydantic`.

### 3.2 Frontend Windows (`frontend/`)

**Stack :** Python 3.13 · PyWebView · Flask local (port 0, choix dynamique) · HTML5 + CSS3 + vanilla JS · SQLite cache

**Écrans :**
1. **Home** — "Où es-tu ?" (GPS auto via Windows Location API + override manuel par sélecteur région) · "Que pêches-tu ?" (15 espèces dropdown avec photos) · "Type d'eau" (lac/rivière/étang/fleuve/baie)
2. **Conditions** (auto-fetched depuis backend + cache) — météo actuelle, pression baro + tendance, phase lune, lever/coucher soleil, fenêtres solunar (vert/jaune/rouge), température eau (si dispo via USGS/ECCC ou input manuel)
3. **Astuces** — output rangé : couleurs leurres recommandées (avec swatches), profondeur, type de leurre, présentation (vitesse récup), structure à viser, fenêtres horaires optimales du jour. Footer = bannière Expedia 320×50.

**Modules :**
- `src/app.py` — entry point PyWebView, gère window + Flask thread
- `src/server.py` — Flask local servant les templates + API proxy vers backend distant
- `src/sync.py` — sync DB locale ↔ backend (delta quotidien sur `tips`/`species`/`color_visibility`)
- `src/geolocation.py` — wrapper Windows Location API + fallback IP (`ipapi.co`)
- `src/cache.py` — gestion cache offline (météo 7 jours, soleil/lune calculé localement)
- `static/css/style.css` — design system (palette : pêche/eau, fonts Inter + JetBrains Mono)
- `static/js/main.js` — interactions, fetch local Flask
- `templates/{home,conditions,tips}.html` — Jinja2

**Dépendances :** `pywebview` 5.x, `flask` 3.x, `requests`, `astral`, `pyinstaller` (build), `winsdk` (geolocation).

### 3.3 Données curées (`data/curated/`)

CSVs versionnés git, source de vérité pour le seed initial :
- `species.csv` — 15 espèces NA (voir §6)
- `regions.csv` — provinces canadiennes + 50 états US (65 lignes)
- `water_types.csv` — 5 types
- `lures.csv` — ~30 leurres avec catégories
- `color_visibility.csv` — matrice turbidité × luminosité × couleur (~120 lignes)
- `tips.csv` — astuces granulaires (~300-500 lignes pour MVP, sources citées colonne `source_url`)

Chaque tip a : `species_id, region_id (nullable, null=global NA), water_type_id, season, baro_trend (enum), moon_phase (enum), temp_water_range, time_of_day, tip_text_fr, tip_text_en, source_url, confidence (1-5)`.

**Sources des tips MVP** (à citer dans `source_url`) :
- Sépaq · Quebec Pêche · Pêches et Océans Canada
- In-Fisherman · Bassmaster · Field & Stream
- Livres référence : "Multi-Species Angler" (Lindner), "Critical Concepts" (In-Fisherman)
- INFOpêche

### 3.4 Deploy (`deploy/`)

- `deploy/i5/setup-i5.ps1` — script PowerShell pour i5 : install Python 3.13, clone repo, créé venv, install deps, configure cloudflared service, démarre uvicorn comme service Windows (NSSM)
- `deploy/i5/cloudflared-config.yml` — tunnel config (V0.1 = quick-tunnel `trycloudflare.com` ; V0.2 = domaine permanent route `pechepro.<domain>` → `localhost:8080`)
- `deploy/windows/installer.iss` — Inno Setup script pour build .exe + installer signé
- `deploy/windows/build.ps1` — orchestre PyInstaller + Inno Setup

## 4. Schéma de base de données (SQLite)

```sql
CREATE TABLE species (
    id INTEGER PRIMARY KEY,
    common_name_fr TEXT NOT NULL,
    common_name_en TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT,
    typical_habitat TEXT,
    image_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE regions (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    country TEXT NOT NULL CHECK(country IN ('CA','US','MX')),
    iso_code TEXT NOT NULL,  -- ex: 'QC', 'ON', 'NY'
    bbox_lat_min REAL,
    bbox_lat_max REAL,
    bbox_lon_min REAL,
    bbox_lon_max REAL
);

CREATE TABLE water_types (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE lures (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,  -- ex: 'soft_plastic', 'crankbait', 'jig', 'spinnerbait', 'fly'
    image_url TEXT
);

CREATE TABLE color_visibility (
    id INTEGER PRIMARY KEY,
    water_clarity TEXT NOT NULL CHECK(water_clarity IN ('clear','stained','muddy')),
    light_level TEXT NOT NULL CHECK(light_level IN ('bright','overcast','dawn_dusk','night')),
    color TEXT NOT NULL,
    visibility_score INTEGER NOT NULL CHECK(visibility_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);

CREATE TABLE tips (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    region_id INTEGER REFERENCES regions(id),  -- nullable = applicable partout
    water_type_id INTEGER REFERENCES water_types(id),
    season TEXT CHECK(season IN ('spring','summer','fall','winter','any')),
    baro_trend TEXT CHECK(baro_trend IN ('rising','falling','steady','any')),
    moon_phase TEXT CHECK(moon_phase IN ('new','waxing','full','waning','any')),
    temp_water_min_c REAL,
    temp_water_max_c REAL,
    time_of_day TEXT CHECK(time_of_day IN ('dawn','morning','midday','afternoon','dusk','night','any')),
    tip_text_fr TEXT NOT NULL,
    tip_text_en TEXT NOT NULL,
    source_url TEXT,
    confidence INTEGER CHECK(confidence BETWEEN 1 AND 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_tips_species ON tips(species_id);
CREATE INDEX idx_tips_lookup ON tips(species_id, region_id, water_type_id, season);

CREATE TABLE solunar_rules (
    id INTEGER PRIMARY KEY,
    period_type TEXT NOT NULL CHECK(period_type IN ('major','minor')),
    duration_minutes INTEGER NOT NULL,
    weight REAL NOT NULL  -- coefficient de qualité 0.0-1.0
);

CREATE TABLE baro_rules (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    baro_trend TEXT NOT NULL CHECK(baro_trend IN ('rising','falling','steady')),
    activity_score INTEGER NOT NULL CHECK(activity_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
```

## 5. Flux de données

### 5.1 Recommandation principale (flux critique)

```
1. User → Home : species_id=walleye, water_type=lake, GPS=46.81,-71.21 (Lévis)
2. App → Backend : POST /v1/recommend {species_id, water_type_id, lat, lon, date}
3. Backend orchestrateur :
   a. → Open-Meteo : météo actuelle + 24h forecast + baro
   b. → astral lib : lever/coucher soleil + phase lune + transits
   c. → solunar.py : calcule major/minor périodes du jour
   d. → recommender.py : query DB tips matching species × region × water × baro_trend × moon_phase
   e. → ranking : score chaque tip par nb de conditions matchées + confidence
4. Backend → App : { weather, baro_trend, sun_moon, solunar_periods, tips_ranked[], lures_recommended[] }
5. App → écran Astuces : render
6. App → cache local : sauvegarde réponse 30 min (clé = species_id + lat/lon arrondi + date)
```

### 5.2 Sync DB locale ↔ backend

Au premier lancement : full clone des tables `species`, `regions`, `water_types`, `lures`, `color_visibility`, `tips`, `solunar_rules`, `baro_rules` (~3 MB).

Quotidien (au lancement si dernier sync >24h) : delta sync via `GET /v1/sync?since=<iso>` → applique upserts.

Si offline : utilise cache local + soleil/lune calculé localement (astral lib embarquée), pas de météo.

## 6. Espèces MVP (15 espèces nord-américaines)

| FR | EN | Scientifique |
|---|---|---|
| Achigan à grande bouche | Largemouth Bass | *Micropterus salmoides* |
| Achigan à petite bouche | Smallmouth Bass | *Micropterus dolomieu* |
| Doré jaune | Walleye | *Sander vitreus* |
| Doré noir | Sauger | *Sander canadensis* |
| Grand brochet | Northern Pike | *Esox lucius* |
| Maskinongé | Muskellunge | *Esox masquinongy* |
| Truite mouchetée | Brook Trout | *Salvelinus fontinalis* |
| Truite arc-en-ciel | Rainbow Trout | *Oncorhynchus mykiss* |
| Truite brune | Brown Trout | *Salmo trutta* |
| Touladi | Lake Trout | *Salvelinus namaycush* |
| Saumon atlantique | Atlantic Salmon | *Salmo salar* |
| Ouananiche | Landlocked Salmon | *Salmo salar (forme dulcicole)* |
| Perchaude | Yellow Perch | *Perca flavescens* |
| Crapet-soleil | Pumpkinseed Sunfish | *Lepomis gibbosus* |
| Barbue de rivière | Channel Catfish | *Ictalurus punctatus* |

## 7. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Backend HS (timeout 5s) | App utilise cache local, bandeau "mode hors ligne" |
| Open-Meteo HS | Backend retourne météo cachée si <30 min, sinon `null` + UI affiche "météo indisponible" |
| GPS refusé par Windows | App demande sélection manuelle de région |
| Aucun tip matchant les conditions exactes | Fallback : tips `region=null + baro=any + moon=any` (générique espèce) |
| DB locale corrompue | Suppression + re-sync full au prochain lancement |
| Cloudflare tunnel down | Backend i5 inaccessible → app full offline (annonce dans UI) |

## 8. Stratégie de tests

**Backend :**
- Unit (pytest) : services solunar, baro_analyzer, recommender, openmeteo_client (mocked)
- Integration : DB seed + endpoints REST (httpx test client)
- Coverage cible : ≥80% lignes
- Smoke test E2E : `pytest -k smoke` lance uvicorn + tape `/v1/recommend` pour walleye à Lévis QC

**Frontend :**
- Unit pytest : sync.py, cache.py, geolocation.py (mocked)
- Smoke test : lance app PyWebView en headless mode, vérifie HTML render

**E2E intégré :**
- Playwright optional Phase 2 (UI complète)
- Pour MVP : test manuel checklist + smoke automatisé

## 9. Monétisation

**Bannière Expedia** (footer écran Astuces) :
- Snippet à porter depuis projet `genia` (à localiser — Master indiquera le chemin)
- Format : 320×50 banner, click-out vers destinations pêche US/Canada (lacs et pourvoiries)
- Chargé async, n'altère pas le launch time
- Si genia introuvable : intégration Expedia Affiliate Network (EAN) directe via affiliate ID Master

**Pas de paywall** dans v0.1. Pas d'achats in-app. Pas de subscription.

## 10. Hors scope (Phase 2+)

- **Phase 2 (post-MVP) :** Web scraper pour enrichir tips, journal de pêche personnel, partage de spots, photos catch
- **Phase 3 :** Espèces sud-américaines (dorado, peacock bass, surubi), app Android/iOS, mode multi-utilisateurs
- **Phase 4 :** Premium tier (météo radar, prédictions IA, communauté), Microsoft Store, App Store mobile

## 11. Risques et mitigations

| Risque | Mitigation |
|---|---|
| **i5 SSH bloqué** (Permission denied historique) | Master fait setup une fois via RDP avec script `setup-i5.ps1` ; pas besoin de SSH récurrent |
| **Pas de domaine Cloudflare** | V0.1 utilise quick-tunnel `*.trycloudflare.com` (URL aléatoire mais gratuit, no domain needed) ; V0.2 migrera vers domaine permanent quand Master en aura un |
| **Open-Meteo rate-limit** (10k calls/jour gratuit) | Cache backend 30 min, cache app 1h, suffit pour <2k users actifs/jour |
| **Données curées incomplètes** (tips manquants pour combinaisons rares) | Fallback tips génériques par espèce, message UI honnête "données limitées pour cette combinaison" |
| **Légalité scraping Phase 2** | Phase 1 = curation manuelle uniquement, sources citées. Scraping Phase 2 fait robots.txt + ToS-compliant (allowlist) |
| **Pub Expedia rejet/délai compte affilié** | Lancement V0.1 sans pub si compte pas prêt, ajout V0.1.1 hot-fix |

## 12. Décomposition implémentation (preview pour writing-plans)

5 plans parallèles à dispatcher :

1. **plan-1-backend-core** — FastAPI bootstrap, schema DB, seed loader, services (solunar, baro, recommender), routes species/regions/astro, tests
2. **plan-2-data-curation** — CSVs `species.csv`, `regions.csv`, `lures.csv`, `color_visibility.csv`, `tips.csv` (~300 tips MVP avec sources)
3. **plan-3-external-apis** — wrappers Open-Meteo, USGS Water, ECCC, route `/v1/weather`, route `/v1/recommend` (orchestrateur)
4. **plan-4-frontend-app** — PyWebView shell, Flask local, écrans Home/Conditions/Astuces, sync, cache, geolocation, design system CSS
5. **plan-5-deploy** — `setup-i5.ps1`, cloudflared service, Inno Setup installer, build script Windows, smoke checklist

Chaque plan = un agent worktree isolé, executor pattern. Merge sur `main` après code-review.

## 13. Critères "done" pour v0.1

- [ ] Backend déployé sur i5, accessible via Cloudflare tunnel public
- [ ] `GET /v1/health` retourne 200 depuis n'importe où
- [ ] `POST /v1/recommend` fonctionne pour les 15 espèces × 5 régions tests
- [ ] DB seed contient ≥300 tips, ≥120 entrées color_visibility
- [ ] App Windows .exe + installer Inno Setup, installable, taille <60 MB
- [ ] App fonctionne offline après 1 sync initial
- [ ] Bannière Expedia visible (ou flag à Phase 2 si compte pas prêt)
- [ ] FR + EN complets pour species, tips, UI strings
- [ ] Tests verts : backend ≥80%, frontend smoke
- [ ] README install : étapes user pour installer l'app + screenshots
- [ ] CHANGELOG.md v0.1.0 daté
