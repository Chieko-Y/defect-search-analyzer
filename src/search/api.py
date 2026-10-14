"""Search API over the SQLite database (FastAPI).

Usage:
    python -m uvicorn api:app --app-dir src/search --port 8000
    → http://127.0.0.1:8000/

先に python src/process/build_db.py で data/processed/defects.db を作っておく。
文章で探す（q）には、さらに python src/process/embed.py でベクトルを作っておく。

窓口（API）:
    GET /api/options               絞り込みの選択肢と件数
    GET /api/complaints            条件で絞り込んだ苦情の一覧（q を付けると、文章の意味が近い順）
    GET /api/complaints/{番号}     1件の詳細
画面（HTML と JavaScript）は web/ にある。分析の画面（/analysis）のグラフも /api/options の件数を使う。
"""
import json
import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "processed" / "defects.db"
WEB_DIR = ROOT / "web"
CHUNKS_PATH = ROOT / "data" / "processed" / "complaint_chunks.jsonl"
EMBEDDINGS_PATH = ROOT / "data" / "processed" / "complaint_chunks.npy"
META_PATH = ROOT / "data" / "processed" / "complaint_chunks_meta.json"  # embed.py がどのモデルで作ったか

# 1位の近さがこれより低いときは、画面に「近い苦情が見つからない」と注意を出す（結果は消さない）。
# 質問セットでは、正解のある質問の1位は 0.49 以上、データにない話題（Android Auto など10個）の1位は
# 0.47 以下だった。正解と外れの苦情は点数が重なるので、結果を消す線にはしない（2026-10-14。Chieko が決定。
# work_log 2章㉞）
LOW_MATCH_SCORE = 0.48


@asynccontextmanager
async def lifespan(app: FastAPI):
    # モデルの読み込みは重い（1分ほど）ので、最初の検索で待たせないよう、起動のときに済ませておく
    try:
        semantic_index()
    except HTTPException as e:
        print(f"注意: 文章での検索は使えません（{e.detail}）")
    yield


app = FastAPI(title="defect-search-analyzer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")  # CSS など


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, "defects.db がありません。先に python src/process/build_db.py を実行してください")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row  # 列の名前で値を取り出せるようにする（row["symptom"]）
    return con


@lru_cache(maxsize=1)
def semantic_index():
    """モデルとベクトルを読み込む（重いので、サーバーの起動のときに1回だけ）"""
    if not CHUNKS_PATH.exists() or not EMBEDDINGS_PATH.exists() or not META_PATH.exists():
        raise HTTPException(500, "ベクトルがありません。先に python src/process/embed.py を実行してください")
    from sentence_transformers import SentenceTransformer  # 読み込みに時間がかかるので、使うときだけ

    with CHUNKS_PATH.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    embeddings = np.load(EMBEDDINGS_PATH)
    if len(chunks) != embeddings.shape[0]:
        raise HTTPException(500, "complaint_chunks の jsonl と npy の件数が合いません。embed.py を実行し直してください")
    # ベクトルを作ったときと同じモデルで質問をベクトルにしないと、比べられない
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    return SentenceTransformer(meta["model"]), meta["query_prefix"], chunks, embeddings


def rank_by_meaning(q: str, odi_numbers: set[int]) -> list[tuple[int, float, str]]:
    """q と意味が近い順に、苦情を並べる → [(番号, 類似度, 一番近かった部分), ...]

    苦情文は小さな部分に分けてベクトルにしてあるので、苦情ごとに一番近い部分の点数を使う。
    odi_numbers（絞り込みの条件に合う苦情）だけを並べる。
    """
    model, query_prefix, chunks, embeddings = semantic_index()
    query_vec = model.encode([query_prefix + q], convert_to_numpy=True, normalize_embeddings=True)[0]
    scores = embeddings @ query_vec  # 正規化してあるので、内積＝コサイン類似度
    best: dict[int, tuple[float, str]] = {}
    for chunk, score in zip(chunks, scores):
        odi = chunk["odi_number"]
        if odi in odi_numbers and (odi not in best or score > best[odi][0]):
            best[odi] = (float(score), chunk["text"])
    return sorted(((odi, sc, text) for odi, (sc, text) in best.items()), key=lambda x: -x[1])


# ---- 画面 ----

@app.get("/")
def index_page():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/detail")
def detail_page():
    return FileResponse(WEB_DIR / "detail.html")


@app.get("/analysis")
def analysis_page():
    return FileResponse(WEB_DIR / "analysis.html")


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
        # 言葉はスペースで区切って、すべてが入っている苦情だけを残す（順番は問わない）
        # 「water leak」なら「water was leaking」も残る。LIKE は英字の大文字・小文字を区別しない
        for word in (self.keyword or "").split():
            where.append("c.summary LIKE ?")
            params.append(f"%{word}%")
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


LIST_COLUMNS = ("c.odi_number, c.model_year, c.date_of_incident, c.powertrain, "
                "c.root_function_group, c.symptom, c.trigger, c.safety_impact, c.evidence")


@app.get("/api/complaints")
def search(filters: Filters = Depends(), q: str | None = None, limit: int = 50, offset: int = 0):
    """条件に合う苦情の一覧

    q（文章）があるときは、条件に合う苦情を、q と意味が近い順に並べる。
    件数は絞り込まない（意味の近さは「どのくらい似ているか」で、合う・合わないの線は引けないため）。
    1位の近さが LOW_MATCH_SCORE より低いときは low_match を true にする（画面が注意を出す）。
    """
    where_sql, params = filters.where()
    limit = min(limit, 200)

    con = connect()
    if not q or not q.strip():
        total = con.execute(f"SELECT COUNT(*) FROM complaints c {where_sql}", params).fetchone()[0]
        rows = con.execute(
            f"SELECT {LIST_COLUMNS} FROM complaints c {where_sql} "
            f"ORDER BY c.safety_impact DESC, c.date_of_incident DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        con.close()
        return {"total": total, "items": [dict(r) for r in rows]}

    odi_numbers = {r[0] for r in con.execute(f"SELECT c.odi_number FROM complaints c {where_sql}", params)}
    ranked = rank_by_meaning(q.strip(), odi_numbers)
    page = ranked[offset:offset + limit]
    rows = {}
    if page:
        marks = ",".join("?" * len(page))
        rows = {r["odi_number"]: dict(r) for r in con.execute(
            f"SELECT {LIST_COLUMNS} FROM complaints c WHERE c.odi_number IN ({marks})",
            [odi for odi, _, _ in page],
        )}
    con.close()
    items = [{**rows[odi], "score": round(score, 3), "matched_text": text} for odi, score, text in page]
    low_match = bool(ranked) and ranked[0][1] < LOW_MATCH_SCORE
    return {"total": len(ranked), "items": items, "low_match": low_match}


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
