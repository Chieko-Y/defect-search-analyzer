"""Classify NHTSA complaints with Claude and save them to data/processed/.

Usage:
    python src/process/classify.py            # data/raw/toyota_rav4_*.json を全件
    python src/process/classify.py 5          # まず5件だけ試す

すでに分類済みの苦情（odiNumber が出力ファイルにあるもの）は飛ばすので、
途中で止まっても同じコマンドで続きから再開できる。
"""
import json
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[2]
RAW_FILES = sorted((ROOT / "data" / "raw").glob("toyota_rav4_20*.json"))
MODEL = "claude-opus-5"
# プロンプトや選択肢を変えたら番号を上げる（どのルールで分類した結果か後から分かるように）
# v1: 最初の版 / v2: environment・multiple_issues・aftermarket_involved を追加、powertrain は VIN で判定（enrich.py）
# v3: 人の目での10件チェックを受けて、safety_impact・trigger・Breakage・機能の分け方のルールを追加
# v4: stated_cause・cause_source を追加、root の優先順位にディーラー/メーカーの診断を追加、
#     原因不明の複数機能の不具合は root を Unknown に、trigger の推測の範囲を具体例で限定、
#     trigger に Driving (road type unknown) を追加（「走行中」だけの苦情用）
# v5: 新しい10件の人の目でのチェックを受けて変更。root は「どの問題か」を顧客の訴えから選び、
#     「どの機能のせいか」をディーラー/メーカーの診断で決める2段階に。safety_impact は root の問題でつける。
#     「異常なし」は cause_source=none、Always は続いていると書かれているときだけ、
#     部品が動かない→Failure to operate、水漏れ→Other、警告でメーターが見えない→IVI/Display
# v6: root のステップ1で、持ち主が一番訴えている問題を優先する（苦情文の目印で判断）
PROMPT_VERSION = "v6"
# バージョンごとに別ファイルに保存し、前の版の結果と比べられるようにする
OUT_PATH = ROOT / "data" / "processed" / f"rav4_classified_{PROMPT_VERSION}.jsonl"

# 選択肢の一覧。プロンプトと出力スキーマの両方にここから入れるので、変えるときはここだけ直す
FUNCTION_GROUPS = [
    "ADAS", "Brakes", "Steering", "Engine", "Transmission/Drivetrain", "Fuel System",
    "Hybrid System", "12V Electrical/Battery", "IVI/Display", "Connectivity",
    "Body/Glass", "HVAC", "Lighting", "Airbags/Restraints", "Tires/Wheels/Suspension", "Other", "Unknown",
]
SYMPTOMS = [
    "Unintended activation", "Failure to operate", "Intermittent operation",
    "False warning", "Display malfunction", "Connection loss", "Noise/Vibration",
    "Performance degradation", "Breakage", "Fire/Smoke", "Other", "Unknown",
]
TRIGGERS = [
    "Highway driving", "City driving", "Driving (road type unknown)", "Low speed/Parking", "Starting from stop",
    "Stationary", "Engine start", "After specific operation", "Always", "Unknown",
]
ENVIRONMENTS = ["Rain", "Snow/Ice", "Heat", "Cold", "None stated"]
CAUSE_SOURCES = ["dealer", "manufacturer", "owner", "none"]
CONFIDENCE = ["high", "medium", "low"]

SYSTEM_PROMPT = f"""You are a vehicle quality analyst. Classify one NHTSA owner complaint.

Rules:
- Use ONLY information written in the complaint. Never guess.
  If something is not stated, use "Unknown" and add the field name to "unclear".
  Exception: trigger may be inferred from context in limited cases (see below).
- "Other" means: stated in the complaint, but no allowed value fits.
- Choose values ONLY from the allowed lists below.
- root_function_group: exactly ONE group. Decide it in two steps.
  Step 1 - choose WHICH problem, from the problems the owner complains about:
  1. If the complaint says A caused B, choose A (e.g. engine stalled, then power steering was lost -> Engine).
     If the owner reports a result (e.g. "replaced the battery and it was fixed"), treat it as A caused B.
  2. If the text shows which problem the owner mainly complains about, choose it. Use only these markers:
     the owner says it is their main concern ("My concern is ..."), asks for a recall/investigation/repair
     of it, repeatedly took the vehicle to the dealer for it, or calls the others secondary
     ("Aside from the leak, ...").
  3. If there is no such marker, choose the problem with the highest safety_impact.
  4. If they are equal, choose the one mentioned first.
  A function that the vehicle itself turned off while showing a reason (e.g. "sensor blocked" in rain
  or snow) is normal behavior, not a problem: do not choose it and do not count it for multiple_issues.
  A dealer diagnosis of a DIFFERENT problem does not change this choice
  (e.g. owner complains about a distorted mirror; the dealer adjusted the alignment -> the mirror).
  Step 2 - choose WHICH function group that problem belongs to:
  - If a dealer/repair shop or the manufacturer identified or repaired the cause of THAT problem,
    use the group of that cause (e.g. stalling diagnosed as a failed fuel injector -> Fuel System).
  - Otherwise, use the group where the symptom appears.
  - An owner's guess alone ("I think it's the battery") does not decide the group.
  Exception: if several functions fail together and no cause is stated (e.g. many warning lights,
  engine stalled, steering became heavy), use root "Unknown", list all groups in
  affected_function_groups, and set multiple_issues = true. Do not fill the root with a guess.
- affected_function_groups: ALL groups mentioned, including the root.
- evidence: copy the shortest phrase from the complaint that supports root_function_group.
- trigger: the vehicle state when the problem occurred (driving, stopped, starting, etc.).
  Infer it only when the situation makes the vehicle state clear:
  "stopped at a red light" -> Stationary; "pulling out of a parking lot" -> Low speed/Parking;
  "driving on the interstate" -> Highway driving.
  Always: only when the complaint states the problem is constant or happens every time
  ("always", "every time", "constantly", "never works"). A part that stopped working, with no
  such statement -> Unknown.
  "While driving" with no road type -> Driving (road type unknown). Use City driving only when
  city streets are stated, and Highway driving only when a highway/freeway/interstate is stated.
  Use Unknown only when it is not even clear whether the vehicle was moving.
  "Got in the car in the morning" without saying whether at start-up or after moving -> Unknown.
- environment: surrounding conditions stated in the complaint. Use "None stated" if none.
- multiple_issues: true if the complaint describes two or more separate problems.
- aftermarket_involved: true if a non-original (aftermarket) part or device is involved.
- stated_cause: the cause or repair written in the complaint, in short English
  (e.g. "Dealer replaced 12V battery", "Software update fixed the issue", "Owner suspects fuel pump").
  Use "" if none is written.
- cause_source: who stated the cause. dealer = dealer or repair shop diagnosis/repair;
  manufacturer = Toyota's explanation, recall or service campaign notice; owner = the owner's own
  opinion; none = no cause written (stated_cause is "").
  If the dealer or manufacturer inspected and found nothing wrong (or said it is normal
  behavior), that is not a cause: cause_source = none (you may note it in stated_cause).
- confidence: how clearly the written content supports the classification.
- Return JSON only, no extra text.

Function group rules (classify by the FUNCTION the part serves, not by the part type):
- Front camera/radar (pre-collision, lane keeping, cruise control), rear/surround cameras,
  parking sensors -> ADAS
- Engine sensors (e.g. O2 sensor) -> Engine; wheel speed sensor (ABS) -> Brakes;
  TPMS -> Tires/Wheels/Suspension; occupant detection sensor -> Airbags/Restraints;
  rain sensor (auto wipers) -> Body/Glass
- Rear camera: if the screen works but only the camera image is missing or distorted -> ADAS.
  If the screen itself goes black or freezes (navigation/radio also unusable) -> IVI/Display.
- A warning message about a function (e.g. "Pre-Collision System malfunction") -> the group of
  that function. But if the owner's complaint is that the warning display hides other information
  (speed, fuel, etc.) -> IVI/Display.
- Aftermarket parts/devices: use the group of the affected function and set
  aftermarket_involved = true (e.g. comma.ai -> ADAS; aftermarket remote starter ->
  12V Electrical/Battery). Set it true only if a non-Toyota part or device is stated to be
  involved. Genuine Toyota accessories installed by a dealer are false.

Symptom rules:
- Breakage: ONLY when the complaint says a part is visibly cracked, shattered, snapped,
  detached, or deformed. Not for internal failures of electronic parts or failures of unknown cause.
- Failure to operate: looks intact but does not work (including cameras/sensors that show
  nothing or do not respond, and parts such as door lock actuators that stopped working).
- Water leaks without visible damage -> Other (not Breakage).
- Noise/Vibration: rattles, squeaks, or shakes but is not broken.
- If a part broke and then stopped working -> Breakage (the cause wins).
- If symptoms progress (e.g. lost power, then stalled), choose the symptom that started it
  (-> Performance degradation).
- False warning: only when the complaint indicates the warning was wrong. If unsure whether the
  function actually failed, choose based on context and lower confidence.

Allowed function_group:
{", ".join(FUNCTION_GROUPS)}

Allowed symptom:
{", ".join(SYMPTOMS)}

Allowed trigger:
{", ".join(TRIGGERS)}

Allowed environment:
{", ".join(ENVIRONMENTS)}

safety_impact (rate the realistic risk that the ROOT problem could cause while driving, not only
what happened this time; other problems in the same complaint do not raise it; use 3 only if a
crash, injury, or fire actually occurred):
- IVI screen goes blank, freezes, or reboots: the rear camera view and warnings shown on the
  screen may be lost -> 2. IVI problems that leave the screen working (audio, navigation,
  phone connection only) -> 1.
0 = inconvenience only
1 = distraction or minor risk
2 = loss of control or risk of collision
3 = crash, injury, or fire actually occurred

confidence: {", ".join(CONFIDENCE)}
"""

# Claude の返答をこの形の JSON に固定する（選択肢以外の値は返ってこない）
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "root_function_group": {"type": "string", "enum": FUNCTION_GROUPS},
        "affected_function_groups": {"type": "array", "items": {"type": "string", "enum": FUNCTION_GROUPS}},
        "symptom": {"type": "string", "enum": SYMPTOMS},
        "trigger": {"type": "string", "enum": TRIGGERS},
        "environment": {"type": "string", "enum": ENVIRONMENTS},
        "safety_impact": {"type": "integer", "enum": [0, 1, 2, 3]},
        "multiple_issues": {"type": "boolean"},
        "aftermarket_involved": {"type": "boolean"},
        "stated_cause": {"type": "string"},
        "cause_source": {"type": "string", "enum": CAUSE_SOURCES},
        "evidence": {"type": "string"},
        "confidence": {"type": "string", "enum": CONFIDENCE},
        "unclear": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "root_function_group", "affected_function_groups", "symptom", "trigger",
        "environment", "safety_impact", "multiple_issues", "aftermarket_involved",
        "stated_cause", "cause_source", "evidence", "confidence", "unclear",
    ],
    "additionalProperties": False,
}


def classify(client: anthropic.Anthropic, summary: str) -> dict:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": summary}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        # 万一 Claude が回答を断ったときは、自動で別のモデルに切り替えてもらう
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"分類できませんでした（stop_reason={response.stop_reason}）")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def load_complaints() -> list[dict]:
    rows = []
    for path in RAW_FILES:
        with open(path, encoding="utf-8") as f:
            rows.extend(json.load(f))
    return rows


def load_done_ids() -> set[int]:
    if not OUT_PATH.exists():
        return set()
    with open(OUT_PATH, encoding="utf-8") as f:
        return {json.loads(line)["odiNumber"] for line in f if line.strip()}


def build_record(r: dict, result: dict, classified_by: str) -> dict:
    """元データの項目（NHTSA が付けたもの）と分類結果を1行分にまとめる"""
    return {
        "odiNumber": r["odiNumber"],
        "model_year": r["products"][0]["productYear"] if r.get("products") else None,
        "dateOfIncident": r.get("dateOfIncident"),
        "dateComplaintFiled": r.get("dateComplaintFiled"),
        "nhtsa_components": r.get("components"),
        "crash": r.get("crash"),
        "fire": r.get("fire"),
        "numberOfInjuries": r.get("numberOfInjuries"),
        "numberOfDeaths": r.get("numberOfDeaths"),
        "summary": r.get("summary"),
        **result,
        "classified_by": classified_by,
        "prompt_version": PROMPT_VERSION,
    }


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) >= 2 else None
    done = load_done_ids()
    todo = [r for r in load_complaints() if r["odiNumber"] not in done][:limit]
    print(f"分類済み {len(done)}件 / 今回 {len(todo)}件")

    client = anthropic.Anthropic()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for i, r in enumerate(todo, 1):
            try:
                result = classify(client, r["summary"])
            except (anthropic.APIError, RuntimeError) as e:
                print(f"[{i}/{len(todo)}] {r['odiNumber']} 失敗: {e}")
                continue
            record = build_record(r, result, classified_by=f"api:{MODEL}")
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i}/{len(todo)}] {r['odiNumber']} {result['root_function_group']} / {result['symptom']}")


if __name__ == "__main__":
    main()
