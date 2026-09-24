"""Make a blank sheet for a human to classify complaints (without showing the AI's answers).

Usage:
    python src/analysis/make_check_sheet.py docs/check_a.md --ids 11761876 11760796 ...
    python src/analysis/make_check_sheet.py docs/check_b.md --random 10 --seed 1

--random は、まだ分類していない苦情（重複を除く）から無作為に選ぶ。
--seed を同じにすれば、何度やっても同じ苦情が選ばれる（あとで検証できるように）。
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "process"))
from classify import (  # noqa: E402
    CAUSE_SOURCES, ENVIRONMENTS, FUNCTION_GROUPS, PROMPT_VERSION, SYMPTOMS, TRIGGERS,
    load_complaints,
)

VEHICLE_INFO = ROOT / "data" / "processed" / "rav4_vehicle_info.jsonl"

HEADER = f"""# 人の目での分類チェック（ルール {PROMPT_VERSION}）

苦情文を読んで、各項目の「→」の後ろに選択肢から1つ書いてください。迷ったら理由をメモ欄に書けば十分です。
AI の分類結果（data/processed/rav4_classified_*.jsonl）は、書き終わるまで見ないでください。

## 選択肢

- root（原因の機能）: {" / ".join(FUNCTION_GROUPS)}
- symptom（症状）: {" / ".join(SYMPTOMS)}
- trigger（起きたときの車の状態）: {" / ".join(TRIGGERS)}
- environment（周りの条件）: {" / ".join(ENVIRONMENTS)}
- safety_impact: 0 = 不便なだけ / 1 = 気が散る・軽い危険 / 2 = 制御を失う・衝突の危険 / 3 = 実際に衝突・けが・火災
- multiple_issues（別々の不具合が2つ以上書かれているか）: true / false
- cause_source（苦情の中で、原因を判断したのは誰か。原因が書かれていなければ none）: {" / ".join(CAUSE_SOURCES)}

## 判断のルール（{PROMPT_VERSION}）

root の選び方（2段階）
ステップ1：どの問題にするか（顧客が訴えている問題から選ぶ）
1. 「A が原因で B が起きた」と書かれていれば A（持ち主が「〇〇を替えたら直った」と結果まで書いていれば、それも含む）
2. 持ち主が一番訴えている問題が、苦情文の目印から分かれば、それ
   （目印：「My concern is 〜」とはっきり書いている／リコール・調査・修理を求めている／何度もディーラーに持ち込んでいる／「Aside from 〜」のように、ほかの問題をついでとして書いている）
3. 目印がなければ、安全への影響が一番大きいもの
4. それも同じなら、最初に書かれているもの
- 車が理由を表示して機能を止めた（雨・雪で「センサーがふさがれた」と出て運転支援が止まった など）のは正常な動作なので、問題に数えない（multiple_issues にも数えない）
ステップ2：その問題がどの機能のせいか
- ディーラー・修理工場・トヨタが、その問題の原因を特定または修理していれば、その機能
- なければ、症状が出ている機能
- 持ち主の推測（「バッテリーだと思う」）だけでは決めない
- 例外：原因が書かれておらず、複数の機能が一度におかしくなった → root は Unknown、multiple_issues は true

trigger
- 状況から車の状態がはっきり分かるときだけ推測してよい（赤信号で停車 → Stationary、駐車場から出る → Low speed/Parking）
- 「走行中」とだけ書かれていて道路の種類が分からない → Driving (road type unknown)
- City driving は街中、Highway driving は高速道路と書かれているときだけ
- 走っていたかどうかも分からない → Unknown
- Always は「いつも」「毎回」「ずっと」など、続いていることがはっきり書かれているときだけ

safety_impact
- root の問題の、起こりうる危険で判断する（同じ苦情のほかの問題は含めない）。3 は実際に衝突・けが・火災が起きたときだけ
- センター画面が消える・固まる・再起動する → 2（リアカメラの映像や警告が見えなくなるため）

symptom
- Breakage は、割れ・折れ・外れ・変形が目で見て分かると書かれているときだけ
- 症状が順に進んだら、最初の症状（パワー低下 → エンスト なら Performance degradation）
- 部品が壊れて動かない（ドアロックのアクチュエーターなど）→ Failure to operate
- 割れていない水漏れ → Other

機能グループ
- 部品の種類ではなく、その部品が担う機能で分ける（前方カメラ → ADAS、車輪速センサー → Brakes など）
- 警告が出ただけの苦情は、警告の対象の機能で分ける。警告のせいでスピードなどが見えないことを訴えていれば IVI/Display
- 後付け品は、影響を受けた機能で分ける

cause_source
- ディーラー・トヨタが調べて「異常なし」「仕様です」と言った → none（原因ではないため）
"""

ITEM = """---

## {n}. {odi}

> {summary}

- root →
- symptom →
- trigger →
- environment →
- safety_impact →
- multiple_issues →
- cause_source →
- メモ →
"""


def pick_random(n: int, seed: int) -> list[int]:
    duplicates = set()
    if VEHICLE_INFO.exists():
        with open(VEHICLE_INFO, encoding="utf-8") as f:
            duplicates = {r["odiNumber"] for r in map(json.loads, f) if r["duplicate_of"]}
    # どの版であれ、一度でも分類した苦情は「見たことがある」ので候補から外す
    done = set()
    for path in (ROOT / "data" / "processed").glob("rav4_classified_*.jsonl"):
        with open(path, encoding="utf-8") as f:
            done |= {json.loads(line)["odiNumber"] for line in f if line.strip()}
    candidates = sorted(r["odiNumber"] for r in load_complaints()
                        if r["odiNumber"] not in done and r["odiNumber"] not in duplicates)
    return random.Random(seed).sample(candidates, n)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--ids", type=int, nargs="+")
    parser.add_argument("--random", type=int)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    ids = args.ids or pick_random(args.random, args.seed)
    rows = {r["odiNumber"]: r for r in load_complaints()}
    text = HEADER + "".join(
        ITEM.format(n=i, odi=odi, summary=rows[odi]["summary"].strip().replace("\n", " "))
        for i, odi in enumerate(ids, 1)
    )
    Path(args.out).write_text(text, encoding="utf-8")
    print("saved:", args.out, ids)


if __name__ == "__main__":
    main()
