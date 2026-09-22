"""Fetch vehicle complaints from the NHTSA public API and save them to data/raw/.

Usage:
    python src/ingest/nhtsa_fetch.py SUBARU OUTBACK 2026
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

API_URL = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def fetch_complaints(make: str, model: str, year: int, retries: int = 3) -> list[dict]:
    # 車種名のスペースを "+" で送ると 503 になるため "%20" でエンコードする
    query = urlencode({"make": make, "model": model, "modelYear": year}, quote_via=quote)
    # NHTSA API は一時的に 503 を返すことがあるので、少し待って再試行する
    for attempt in range(retries):
        r = requests.get(f"{API_URL}?{query}", timeout=30)
        if r.status_code < 500 or attempt == retries - 1:
            break
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    return r.json().get("results", [])


def main() -> None:
    make, model, year = (sys.argv[1:4] if len(sys.argv) >= 4 else ("SUBARU", "OUTBACK", "2026"))
    rows = fetch_complaints(make, model, int(year))
    print(make, model, year, len(rows), "件")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{make.lower()}_{model.lower().replace(' ', '-')}_{year}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("saved:", out)


if __name__ == "__main__":
    main()
