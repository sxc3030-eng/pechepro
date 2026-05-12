"""Assembler for tips.csv.

Reads `_tips_data.TIPS` (a list of dict rows), assigns sequential ids, and
writes UTF-8-BOM/LF CSV to data/curated/tips.csv. Idempotent.
"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from _tips_data import TIPS  # type: ignore[import-not-found]

HEADERS = [
    "id",
    "species_id",
    "region_id",
    "water_type_id",
    "season",
    "baro_trend",
    "moon_phase",
    "temp_water_min_c",
    "temp_water_max_c",
    "time_of_day",
    "tip_text_fr",
    "tip_text_en",
    "source_url",
    "confidence",
]


def main() -> None:
    out = StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(HEADERS)
    for i, t in enumerate(TIPS, start=1):
        w.writerow([i] + [t.get(h, "") for h in HEADERS[1:]])
    path = Path(__file__).resolve().parents[1] / "data" / "curated" / "tips.csv"
    with path.open("wb") as fh:
        fh.write(b"\xef\xbb\xbf")
        fh.write(out.getvalue().encode("utf-8"))
    print(f"wrote {len(TIPS)} tips to {path}")


if __name__ == "__main__":
    main()
