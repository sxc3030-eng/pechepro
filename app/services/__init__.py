"""In-process service layer for pechepro.

Each module exposes a small public API consumed by the Flask routes in
app.server. Services are isolated from each other (no cross-imports beyond
app.db where needed) and all external I/O (network, OS calls) is mockable
for tests.

Canonical signatures locked in docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md.
"""
