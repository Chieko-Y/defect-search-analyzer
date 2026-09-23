"""Helper for classifying complaints by hand (without the API), in classify.py's format.

Usage:
    python src/process/manual_classify.py next 30          # 未分類の苦情を30件表示（部品カテゴリは出さない）
    python src/process/manual_classify.py save batch.json  # 分類結果をチェックして rav4_classified_v2.jsonl に追記（版は classify.py の PROMPT_VERSION）

batch.json は [{"odiNumber": 123, "root_function_group": ..., ...}, ...] の形。
選択肢にない値や項目の抜けがあれば、1件も保存せずにエラーを表示する。
"""
import json
import sys

from classify import OUT_PATH, OUTPUT_SCHEMA, build_record, load_complaints, load_done_ids

CLASSIFIED_BY = "claude-code-manual"


def show_next(n: int) -> None:
    done = load_done_ids()
    todo = [r for r in load_complaints() if r["odiNumber"] not in done]
    print(f"未分類 {len(todo)}件のうち {min(n, len(todo))}件\n")
    # 分類の判断に影響しないよう、NHTSA の部品カテゴリや衝突フラグは表示しない
    for r in todo[:n]:
        print(f"### {r['odiNumber']}")
        print(r.get("summary", ""))
        print()


def check(item: dict) -> list[str]:
    """classify.py の OUTPUT_SCHEMA と同じ条件でチェックする（スキーマを変えればここも自動で変わる）"""
    errors = []
    keys = set(OUTPUT_SCHEMA["required"]) | {"odiNumber"}
    if set(item) != keys:
        errors.append(f"項目が違う: 不足={keys - set(item)} 余分={set(item) - keys}")
        return errors
    for key, spec in OUTPUT_SCHEMA["properties"].items():
        value = item[key]
        if spec["type"] == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} が true/false でない: {value!r}")
        elif "enum" in spec and value not in spec["enum"]:
            errors.append(f"{key} が選択肢にない: {value!r}")
        elif spec["type"] == "array" and "enum" in spec["items"]:
            bad = [v for v in value if v not in spec["items"]["enum"]]
            if bad:
                errors.append(f"{key} が選択肢にない: {bad}")
    # root が Unknown のときは、affected には苦情に出てくる機能だけを入れる（v4 のルール）
    if item["root_function_group"] != "Unknown" and item["root_function_group"] not in item["affected_function_groups"]:
        errors.append("affected_function_groups に root_function_group が入っていない")
    return errors


def save(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    raw = {r["odiNumber"]: r for r in load_complaints()}
    done = load_done_ids()

    problems = []
    for item in items:
        odi = item.get("odiNumber")
        if odi not in raw:
            problems.append(f"{odi}: 元データにない odiNumber")
        elif odi in done:
            problems.append(f"{odi}: すでに分類済み")
        else:
            problems += [f"{odi}: {e}" for e in check(item)]
            # evidence は苦情文からそのまま写すルールなので、本文に含まれているか確かめる
            if item.get("evidence") not in raw[odi].get("summary", ""):
                problems.append(f"{odi}: evidence が苦情文にない: {item.get('evidence')!r}")
    if problems:
        print("保存しませんでした:\n  " + "\n  ".join(problems))
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for item in items:
            result = {k: v for k, v in item.items() if k != "odiNumber"}
            record = build_record(raw[item["odiNumber"]], result, classified_by=CLASSIFIED_BY)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{len(items)}件を保存しました（合計 {len(done) + len(items)}件）")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "next":
        show_next(int(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "save":
        save(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
