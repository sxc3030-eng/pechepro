# Changelog

All notable changes to pechepro will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-12

### Added
- First public alpha of pechepro
- Standalone Windows desktop app (PyWebView + Flask local)
- Personalized fishing recommendations by species x region x baro x moon x solunar
- 15 North American species : achigan grande/petite bouche, dore jaune/noir, brochet, maskinonge, truite mouchetee/arc-en-ciel/brune, touladi, saumon atlantique, ouananiche, perchaude, crapet-soleil, barbue de riviere
- 65 regions across Canada (13), US (50), and Mexico border states (2)
- 310 curated fishing tips with source citations (Sepaq, Quebec Peche, In-Fisherman, Bassmaster, Field & Stream, Lindner books)
- FR + EN UI with auto language detection
- Offline-capable : 100% local SQLite cache + astral sun/moon calculations
- Live Open-Meteo weather + barometric pressure with 1h cache
- USGS water temperature for US regions, ECCC for Canada
- Expedia Affiliate Banners footer widget (camref 1101l5IQud, pubref pechepro-tips)
- GitHub raw CSV sync every 24h — tips refresh without app reinstall

### Known limitations
- Code signing certificate not yet acquired — SmartScreen warning on first launch (click "Run anyway")
- ECCC water temperature coverage is sparse (mostly Canadian flow stations report it only as metadata)
- Tip sources include landing-page URLs in some cases — V0.2 will deep-link individual articles
- Region-specific tips currently focus on Quebec (id=11) ; V0.2 will expand to Ontario, NY, Maine, Minnesota

### Build info
- Python 3.13 · PyWebView 5.4 · Flask 3.0.3 · SQLite stdlib
- 311 pytest tests, ~96% coverage on services
- Built via PyInstaller 6.11.1 + Inno Setup 6 + GitHub Actions on windows-latest

### Acknowledgements
- Bootstrapped via the Claude Code superpowers plugin (brainstorming -> writing-plans -> subagent-driven-development workflow)
