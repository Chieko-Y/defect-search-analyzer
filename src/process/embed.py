"""Turn each complaint text into vectors for the meaning-based search (③).

Usage:
    python src/process/embed.py

先に python src/process/build_db.py で defects.db を作っておく。

出力（どちらも DB から何度でも作れるので Git には入れない）:
    data/processed/complaint_chunks.jsonl  苦情文を分けた部分（1行1つ: odi_number, text）
    data/processed/complaint_chunks.npy   各部分の意味の数字（ベクトル）。行の順番は jsonl と同じ
    data/processed/complaint_chunks_meta.json  どのモデルで作ったか（検索の API は、これを見て同じモデルを使う）

なぜ分けるのか:
    最初のモデル（MiniLM）が一度に読めるのは 128 トークン（英語でおよそ 90 語）まで。苦情文の半分
    （273/555件）はそれより長く、そのままだと後半が無視される。そこで文の切れ目で 100 トークン以内の
    部分に分け、検索では苦情ごとに「一番近い部分」の点数を使う。どの部分が近かったかも画面に出せる。
    いまの e5-base は 512 トークンまで読めるが、近かった部分を短く示せるので、分け方はそのままにしている。
"""
import json
import re
import sqlite3

import numpy as np
from sentence_transformers import SentenceTransformer

from classify import ROOT

DB_PATH = ROOT / "data" / "processed" / "defects.db"
CHUNKS_PATH = ROOT / "data" / "processed" / "complaint_chunks.jsonl"
EMBEDDINGS_PATH = ROOT / "data" / "processed" / "complaint_chunks.npy"
META_PATH = ROOT / "data" / "processed" / "complaint_chunks_meta.json"

# 多言語に対応しているので、日本語の質問で英語の苦情を探せる。
# 最初は「仕様書類似検索」アプリと同じ paraphrase-multilingual-MiniLM-L12-v2 だったが、
# テスト用の質問セット（data/eval/search_queries.json）で比べて、点数が高かったこちらにした（44% → 50%）
MODEL_NAME = "intfloat/multilingual-e5-base"
# e5 は、探される文に "passage: "、質問に "query: " を付ける決まりがある
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
MAX_TOKENS = 100  # 最初のモデルの上限 128 より少し小さくしておく（モデルを比べたときと同じ分け方）


WORDS_PER_PIECE = 50  # 句点がなく長すぎる文を区切るときの語数


def split_sentences(text: str, count_tokens) -> list[str]:
    """. ! ? のあとの空白で文に分ける（略語で切れることもあるが、検索には十分）

    句点がなく MAX_TOKENS を超える文は、語数で区切る
    """
    sentences = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        s = s.strip()
        if not s:
            continue
        if count_tokens(s) <= MAX_TOKENS:
            sentences.append(s)
        else:
            words = s.split()
            sentences += [" ".join(words[i:i + WORDS_PER_PIECE]) for i in range(0, len(words), WORDS_PER_PIECE)]
    return sentences


def make_chunks(text: str, count_tokens) -> list[str]:
    """文を前から順に詰めて、MAX_TOKENS 以内の部分にまとめる"""
    chunks, current = [], []
    for sentence in split_sentences(text, count_tokens):
        if current and count_tokens(" ".join(current + [sentence])) > MAX_TOKENS:
            chunks.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks


def main():
    con = sqlite3.connect(DB_PATH)
    complaints = con.execute("SELECT odi_number, summary FROM complaints ORDER BY odi_number").fetchall()
    con.close()

    model = SentenceTransformer(MODEL_NAME)
    count_tokens = lambda s: len(model.tokenizer(s)["input_ids"])

    chunks = []
    for odi_number, summary in complaints:
        for text in make_chunks(summary or "", count_tokens):
            chunks.append({"odi_number": odi_number, "text": text})

    # normalize_embeddings=True にしておくと、内積（@）がそのままコサイン類似度になる
    embeddings = model.encode([PASSAGE_PREFIX + c["text"] for c in chunks], batch_size=32, show_progress_bar=True,
                              convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)

    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    np.save(EMBEDDINGS_PATH, embeddings)
    META_PATH.write_text(json.dumps({"model": MODEL_NAME, "query_prefix": QUERY_PREFIX}, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    print(f"苦情: {len(complaints)} 件 → 部分: {len(chunks)} 個（1件あたり平均 {len(chunks) / len(complaints):.1f} 個）")
    print(f"ベクトル: {embeddings.shape}  → {EMBEDDINGS_PATH}")


if __name__ == "__main__":
    main()
