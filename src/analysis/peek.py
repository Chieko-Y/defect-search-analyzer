"""Print complaints from a raw JSON file in a readable form.

Usage:
    python src/analysis/peek.py data/raw/subaru_outback-ice_2026.json [件数]
    (引数なしの場合は DEFAULT_PATH を表示)
"""
import json
import sys
import textwrap
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "subaru_outback-ice_2026.json"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_PATH
    limit = int(sys.argv[2]) if len(sys.argv) >= 3 else 20
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)

    print(f"{path}: 全{len(rows)}件のうち{min(limit, len(rows))}件を表示\n")
    for i, r in enumerate(rows[:limit], 1):
        flags = [name for name in ("crash", "fire") if r.get(name)]
        if r.get("numberOfInjuries"):
            flags.append(f"injuries={r['numberOfInjuries']}")
        print(f"[{i}] {r.get('dateOfIncident')}  {r.get('components')}  {' '.join(flags)}")
        print(textwrap.fill(r.get("summary", ""), width=100, initial_indent="    ", subsequent_indent="    "))
        print()


if __name__ == "__main__":
    main()
