"""Score the meaning-based search with the test queries in data/eval/search_queries.json.

Usage:
    python src/analysis/eval_search.py                      # アプリで使っているモデル（embed.py で作ったベクトル）
    python src/analysis/eval_search.py intfloat/multilingual-e5-small   # 別のモデルで試す

先に build_db.py と embed.py を実行しておく。どのモデルでも、embed.py で分けた同じ部分
（complaint_chunks.jsonl）を使うので、違いはモデルだけになる。

2026-10-01 の結果（合計）: paraphrase-multilingual-MiniLM-L12-v2 44% / multilingual-e5-small 44% /
multilingual-e5-base 50% → e5-base をアプリに採用（10/13 に MiniLM に戻した。下を参照）

点数: 上位10件のうち、正解（分類の条件に合う苦情）が何件入ったか。アプリと同じく二重登録は除く。

2026-10-13 から、並べ方を3通りで比べる（日本語の言い方と英語の言い方それぞれで）:
    意味        意味の近さだけ（いままでのやり方）
    キーワード  言葉が合っているかだけ（BM25）
    組み合わせ  2つの順位を組み合わせる（ハイブリッド検索。src/search/hybrid.py）

2026-10-13 の結果（e5-base）: 日本語 意味 50%／キーワード 0%／組み合わせ 50%、
英語 意味 62%／キーワード 58%／組み合わせ 64%。キーワードは短い言い方でしか効かず、文章では変わらない
→ アプリはセマンティック検索（意味だけ）のまま。MiniLM は 日本語 44%・英語 61%。
e5-base との差がわずかなので、前のアプリと同じ MiniLM にそろえた
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "search"))
from hybrid import KeywordIndex, fuse  # noqa: E402  アプリと同じ部品を使う

DB_PATH = ROOT / "data" / "processed" / "defects.db"
CHUNKS_PATH = ROOT / "data" / "processed" / "complaint_chunks.jsonl"
EMBEDDINGS_PATH = ROOT / "data" / "processed" / "complaint_chunks.npy"
META_PATH = ROOT / "data" / "processed" / "complaint_chunks_meta.json"
QUERIES_PATH = ROOT / "data" / "eval" / "search_queries.json"
CACHE_DIR = ROOT / "data" / "eval" / "cache"  # モデルごとのベクトル（作り直せるので Git には入れない）

TOP_N = 10

# e5 系のモデルは、質問に "query: "、探される文に "passage: " を付ける決まりがある
PREFIXES = {"intfloat/": ("query: ", "passage: ")}


def prefixes(model_name: str) -> tuple[str, str]:
    for start, pair in PREFIXES.items():
        if model_name.startswith(start):
            return pair
    return "", ""


def app_model() -> str:
    return json.loads(META_PATH.read_text(encoding="utf-8"))["model"]


def chunk_embeddings(model, model_name: str, texts: list[str]) -> np.ndarray:
    if model_name == app_model():
        return np.load(EMBEDDINGS_PATH)  # embed.py で作ったものをそのまま使う
    cache = CACHE_DIR / (model_name.replace("/", "__") + ".npy")
    if cache.exists():
        embeddings = np.load(cache)
        if embeddings.shape[0] == len(texts):
            return embeddings
    _, passage = prefixes(model_name)
    embeddings = model.encode([passage + t for t in texts], batch_size=32, show_progress_bar=True,
                              convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(cache, embeddings)
    return embeddings


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    model_name = sys.argv[1] if len(sys.argv) > 1 else app_model()

    with CHUNKS_PATH.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    topics = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["topics"]

    con = sqlite3.connect(DB_PATH)
    searchable = {r[0] for r in con.execute("SELECT odi_number FROM complaints WHERE duplicate_of IS NULL")}

    model = SentenceTransformer(model_name)
    embeddings = chunk_embeddings(model, model_name, [c["text"] for c in chunks])
    query_prefix, _ = prefixes(model_name)

    keyword_index = KeywordIndex({r[0]: r[1] or "" for r in con.execute(
        "SELECT odi_number, summary FROM complaints WHERE duplicate_of IS NULL")})

    def rankings(q: str) -> dict[str, list[int]]:
        vec = model.encode([query_prefix + q], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = embeddings @ vec
        best: dict[int, float] = {}  # 苦情ごとに、一番近い部分の点数（アプリと同じ）
        for chunk, score in zip(chunks, scores):
            odi = chunk["odi_number"]
            if odi in searchable and score > best.get(odi, -1.0):
                best[odi] = float(score)
        meaning = sorted(best, key=lambda odi: -best[odi])
        kw = keyword_index.scores(q, searchable)
        keyword = sorted(kw, key=lambda odi: -kw[odi])
        return {"意味": meaning, "キーワード": keyword, "組み合わせ": fuse(meaning, keyword)}

    methods = ["意味", "キーワード", "組み合わせ"]
    langs = [("日本語", "queries"), ("英語", "queries_en")]
    totals = {(lang, m): [0, 0] for lang, _ in langs for m in methods}
    print(f"モデル: {model_name}\n")
    print(f"各欄: 上位{TOP_N}件中の正解（最初の正解の順位。- は正解が出てこない）\n")
    print("| # | テーマ | 探す文 | 正解の数 | " + " | ".join(methods) + " |")
    print("|---|---|---|---|" + "---|" * len(methods))
    for topic in topics:
        answer = {r[0] for r in con.execute(
            f"SELECT c.odi_number FROM complaints c WHERE c.duplicate_of IS NULL AND ({topic['answer']})")}
        possible = min(TOP_N, len(answer))
        for lang, key in langs:
            for q in topic.get(key, []):
                cells = []
                for m, ranking in rankings(q).items():
                    hits = sum(odi in answer for odi in ranking[:TOP_N])
                    first = next((i + 1 for i, odi in enumerate(ranking) if odi in answer), "-")
                    totals[(lang, m)][0] += hits
                    totals[(lang, m)][1] += possible
                    cells.append(f"{hits}/{possible} ({first})")
                print(f"| {topic['id']} | {topic['name']} | {q} | {len(answer)} | " + " | ".join(cells) + " |")
    con.close()

    print("\n合計")
    print("| 言い方 | " + " | ".join(methods) + " |")
    print("|---|" + "---|" * len(methods))
    for lang, _ in langs:
        cells = [f"{h} / {n}（{h / n:.0%}）" for h, n in (totals[(lang, m)] for m in methods)]
        print(f"| {lang} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
