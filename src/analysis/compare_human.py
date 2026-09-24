"""Compare a human-filled check sheet (docs/human_check_10.md) with the classified data.

Usage:
    python src/analysis/compare_human.py [docs/human_check_10.md] [data/processed/rav4_classified_v2.jsonl]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ["root", "symptom", "trigger", "environment", "safety_impact", "multiple_issues", "cause_source"]
# チェックシートの項目名 → 分類データの項目名
DATA_KEY = {"root": "root_function_group"}


def read_sheet(path: Path) -> dict[int, dict]:
    answers, odi = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"## \d+\. (\d+)", line):
            odi = int(m.group(1))
            answers[odi] = {}
        elif odi and (m := re.match(r"- (\w+) →(.*)", line)):
            answers[odi][m.group(1)] = m.group(2).strip()
    return answers


# 人が書いたときの表記ゆれ・打ち間違い → 選択肢の正しい書き方
ALIASES = {"not stated": "none stated", "ture": "true", "btransmission/drivetrain": "transmission/drivetrain"}


def normalize(value) -> str:
    v = str(value).strip().lower()
    return ALIASES.get(v, v)


def main() -> None:
    sheet = Path(sys.argv[1]) if len(sys.argv) >= 2 else ROOT / "docs" / "human_check_10.md"
    data = Path(sys.argv[2]) if len(sys.argv) >= 3 else ROOT / "data" / "processed" / "rav4_classified_v2.jsonl"
    human = read_sheet(sheet)
    with open(data, encoding="utf-8") as f:
        ai = {r["odiNumber"]: r for r in map(json.loads, f) if r["odiNumber"] in human}

    # 古いチェックシートには無い項目もあるので、シートに書かれている項目だけ比べる
    fields = [f for f in FIELDS if any(f in h for h in human.values())]
    match = {f: 0 for f in fields}
    for odi, h in human.items():
        diffs = []
        for f in fields:
            a = ai[odi][DATA_KEY.get(f, f)]
            if normalize(h.get(f, "")) == normalize(a):
                match[f] += 1
            else:
                diffs.append(f"{f}: 人={h.get(f)!s} / AI={a}")
        print(f"{odi}  " + ("一致" if not diffs else " | ".join(diffs)))

    print(f"\n項目ごとの一致率（{len(human)}件）")
    for f in fields:
        print(f"  {f:16} {match[f]}/{len(human)}")


if __name__ == "__main__":
    main()
