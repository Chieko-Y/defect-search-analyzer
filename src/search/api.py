"""Search API over the SQLite database (FastAPI).

Usage:
    python -m uvicorn api:app --app-dir src/search --port 8000
    → http://127.0.0.1:8000/

先に python src/process/build_db.py で data/processed/defects.db を作っておく。

窓口（API）:
    GET /api/options               絞り込みの選択肢と件数
    GET /api/complaints            条件で絞り込んだ苦情の一覧
    GET /api/complaints/{番号}     1件の詳細
画面（HTML と JavaScript）は web/ にある。
"""
import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "processed" / "defects.db"
WEB_DIR = ROOT / "web"

app = FastAPI(title="defect-search-analyzer")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")  # CSS など


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, "defects.db がありません。先に python src/process/build_db.py を実行してください")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row  # 列の名前で値を取り出せるようにする（row["symptom"]）
    return con


# ---- 画面 ----

@app.get("/")
def index_page():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/detail")
def detail_page():
    return FileResponse(WEB_DIR / "detail.html")


# ---- API ----

# 絞り込みに使う complaints の列（画面の名前 → DB の列）
FILTER_COLUMNS = {
    "root": "root_function_group",
    "symptom": "symptom",
    "trigger": "trigger",
    "environment": "environment",
    "powertrain": "powertrain",
    "model_year": "model_year",
    "safety_impact": "safety_impact",
}


class Filters:
    """画面で選んだ条件（URL のパラメータ）。一覧の検索と、選択肢の件数の両方で使う"""

    def __init__(
        self,
        root: str | None = None,
        function: str | None = None,
        symptom: str | None = None,
        trigger: str | None = None,
        environment: str | None = None,
        powertrain: str | None = None,
        model_year: int | None = None,
        safety_impact: int | None = None,
        keyword: str | None = None,
        include_duplicates: bool = False,
    ):
        self.values = {"root": root, "function": function, "symptom": symptom, "trigger": trigger,
                       "environment": environment, "powertrain": powertrain,
                       "model_year": model_year, "safety_impact": safety_impact}
        self.keyword = keyword
        self.include_duplicates = include_duplicates

    def where(self, skip: str | None = None) -> tuple[str, list]:
        """条件を SQL の WHERE にする。条件は AND でつなぐ（指定しなかった条件は使わない）

        skip: この項目の条件だけ使わない（その項目の選択肢を数えるとき用）
        """
        where, params = [], []
        for name, value in self.values.items():
            if name == skip or value is None or value == "":
                continue
            if name == "function":
                # root だけでなく、一緒に出てきた機能（サブ）も含めて探す
                where.append("EXISTS (SELECT 1 FROM complaint_functions f2 "
                             "WHERE f2.odi_number = c.odi_number AND f2.function_group = ?)")
            else:
                where.append(f"c.{FILTER_COLUMNS[name]} = ?")
            params.append(value)
        if self.keyword:
            where.append("c.summary LIKE ?")
            params.append(f"%{self.keyword}%")
        if not self.include_duplicates:
            where.append("c.duplicate_of IS NULL")
        return ("WHERE " + " AND ".join(where) if where else ""), params


@app.get("/api/options")
def options(filters: Filters = Depends()):
    """それぞれの絞り込み項目に、どんな値が何件あるか

    ほかの項目で選んだ条件に合う苦情だけを数える（例: root に IVI/Display を選ぶと、
    症状の選択肢は IVI/Display の苦情に出てくるものだけになる）。
    自分の項目の条件は外して数えるので、選んだあとでも別の値に選び直せる。
    """
    con = connect()
    result = {}
    for name, column in FILTER_COLUMNS.items():
        where_sql, params = filters.where(skip=name)
        # 列の名前は上の表から選んだものだけなので、SQL に直接入れてよい
        rows = con.execute(
            f"SELECT c.{column} AS value, COUNT(*) AS n FROM complaints c {where_sql} "
            f"GROUP BY c.{column} ORDER BY n DESC",
            params,
        ).fetchall()
        result[name] = [dict(r) for r in rows]
    where_sql, params = filters.where(skip="function")
    rows = con.execute(
        "SELECT f.function_group AS value, COUNT(*) AS n "
        f"FROM complaint_functions f JOIN complaints c ON c.odi_number = f.odi_number {where_sql} "
        "GROUP BY f.function_group ORDER BY n DESC",
        params,
    ).fetchall()
    result["function"] = [dict(r) for r in rows]
    con.close()
    return result


@app.get("/api/complaints")
def search(filters: Filters = Depends(), limit: int = 50, offset: int = 0):
    """条件に合う苦情の一覧"""
    where_sql, params = filters.where()

    con = connect()
    total = con.execute(f"SELECT COUNT(*) FROM complaints c {where_sql}", params).fetchone()[0]
    rows = con.execute(
        f"SELECT c.odi_number, c.model_year, c.date_of_incident, c.powertrain, "
        f"c.root_function_group, c.symptom, c.trigger, c.safety_impact, c.evidence "
        f"FROM complaints c {where_sql} "
        f"ORDER BY c.safety_impact DESC, c.date_of_incident DESC LIMIT ? OFFSET ?",
        params + [min(limit, 200), offset],
    ).fetchall()
    con.close()
    return {"total": total, "items": [dict(r) for r in rows]}


@app.get("/api/complaints/{odi_number}")
def detail(odi_number: int):
    """1件の詳細。関係する機能には、root（メイン）かどうかの印を付けて返す"""
    con = connect()
    row = con.execute("SELECT * FROM complaints WHERE odi_number = ?", (odi_number,)).fetchone()
    if row is None:
        con.close()
        raise HTTPException(404, f"苦情 {odi_number} は見つかりません")
    functions = con.execute(
        "SELECT f.function_group, f.function_group = c.root_function_group AS is_root "
        "FROM complaint_functions f JOIN complaints c ON c.odi_number = f.odi_number "
        "WHERE f.odi_number = ? ORDER BY is_root DESC, f.function_group",
        (odi_number,),
    ).fetchall()
    components = con.execute(
        "SELECT component FROM complaint_components WHERE odi_number = ? ORDER BY component",
        (odi_number,),
    ).fetchall()
    con.close()
    return {
        **dict(row),
        "functions": [{"name": f["function_group"], "is_root": bool(f["is_root"])} for f in functions],
        "components": [c["component"] for c in components],
    }
