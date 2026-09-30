"""Load the v7 classification results and vehicle info into SQLite for the search app.

Usage:
    python src/process/build_db.py

出力: data/processed/defects.db（毎回作り直す。JSONL から何度でも作れるので Git には入れない）

表:
    complaints            苦情1件が1行（NHTSA の元データ＋分類＋VIN の結果）
    complaint_functions   影響した機能（affected_function_groups）を1行1つずつ
    complaint_components  NHTSA の部品カテゴリ（nhtsa_components）を1行1つずつ
"""
import json
import sqlite3
from datetime import datetime

from classify import ROOT

CLASSIFIED = ROOT / "data" / "processed" / "rav4_classified_v7.jsonl"
VEHICLE_INFO = ROOT / "data" / "processed" / "rav4_vehicle_info.jsonl"
DB_PATH = ROOT / "data" / "processed" / "defects.db"

SCHEMA = """
CREATE TABLE complaints (
    odi_number          INTEGER PRIMARY KEY,
    model_year          INTEGER,
    date_of_incident    TEXT,     -- YYYY-MM-DD（並べ替え・月ごとの集計ができる形）
    date_filed          TEXT,
    summary             TEXT,
    crash               INTEGER,  -- 0/1（SQLite には真偽の型がない）
    fire                INTEGER,
    injuries            INTEGER,
    deaths              INTEGER,
    root_function_group TEXT,
    symptom             TEXT,
    trigger             TEXT,
    environment         TEXT,
    safety_impact       INTEGER,
    multiple_issues     INTEGER,
    aftermarket_involved INTEGER,
    stated_cause        TEXT,
    cause_source        TEXT,
    evidence            TEXT,
    confidence          TEXT,
    unclear             TEXT,     -- 検索には使わないので JSON の文字列のまま
    other_detail        TEXT,
    prompt_version      TEXT,
    powertrain          TEXT,     -- VIN から判定（gas / hybrid / plug-in hybrid / unknown）
    trim                TEXT,
    duplicate_of        INTEGER   -- 二重登録なら最初の苦情の番号
);

CREATE TABLE complaint_functions (
    odi_number     INTEGER REFERENCES complaints(odi_number),
    function_group TEXT,
    PRIMARY KEY (odi_number, function_group)
);

CREATE TABLE complaint_components (
    odi_number INTEGER REFERENCES complaints(odi_number),
    component  TEXT,
    PRIMARY KEY (odi_number, component)
);

CREATE INDEX idx_functions_group ON complaint_functions(function_group);
CREATE INDEX idx_components_component ON complaint_components(component);
"""


def iso_date(s: str | None) -> str | None:
    """NHTSA の日付（MM/DD/YYYY）を YYYY-MM-DD に直す"""
    if not s:
        return None
    return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")


def read_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    rows = read_jsonl(CLASSIFIED)
    vehicles = {v["odiNumber"]: v for v in read_jsonl(VEHICLE_INFO)}

    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    for r in rows:
        v = vehicles.get(r["odiNumber"], {})
        con.execute(
            "INSERT INTO complaints VALUES (" + ",".join("?" * 26) + ")",
            (
                r["odiNumber"], int(r["model_year"]),
                iso_date(r.get("dateOfIncident")), iso_date(r.get("dateComplaintFiled")),
                r.get("summary"),
                int(r["crash"]), int(r["fire"]), r["numberOfInjuries"], r["numberOfDeaths"],
                r["root_function_group"], r["symptom"], r["trigger"], r["environment"],
                r["safety_impact"], int(r["multiple_issues"]), int(r["aftermarket_involved"]),
                r["stated_cause"], r["cause_source"], r["evidence"], r["confidence"],
                json.dumps(r["unclear"], ensure_ascii=False), r["other_detail"], r["prompt_version"],
                v.get("powertrain_vin", "unknown"), v.get("vin_trim"), v.get("duplicate_of"),
            ),
        )
        # 同じ機能が2回書かれていても1行にする
        for fg in dict.fromkeys(r["affected_function_groups"]):
            con.execute("INSERT INTO complaint_functions VALUES (?, ?)", (r["odiNumber"], fg))
        components = [c.strip() for c in (r.get("nhtsa_components") or "").split(",") if c.strip()]
        for c in dict.fromkeys(components):
            con.execute("INSERT INTO complaint_components VALUES (?, ?)", (r["odiNumber"], c))

    con.commit()

    for table in ("complaints", "complaint_functions", "complaint_components"):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {n} 行")
    con.close()
    print("saved:", DB_PATH)


if __name__ == "__main__":
    main()
