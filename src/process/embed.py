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

# 多言語に対応しているので、日本語の質問で英語の苦情を探せる。「仕様書類似検索」アプリと同じモデル。
# 10/1〜10/13 は multilingual-e5-base を使っていた。質問セット（data/eval/search_queries.json）では
# 英語でほぼ同じ（61% と 62%）、日本語で e5-base が少し上（44% と 50%）だったが、差がわずかなので、
# 前のアプリと同じこちらにそろえた
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# e5 のモデルでは、探される文に "passage: "、質問に "query: " を付ける決まりがある。MiniLM は付けない
PASSAGE_PREFIX = ""
QUERY_PREFIX = ""
MAX_TOKENS = 100  # MiniLM の上限 128 より少し小さくしておく


WORDS_PER_PIECE = 50  # 句点がなく長すぎる文を区切るときの語数

# 個人情報を黒塗りにしたときに NHTSA が付ける決まり文句（41件）と、名前や日付を隠した印（[XXX] など）。
# 苦情の中身とは関係がないので、ベクトルにする前に除く。除かないと「information」などで探したとき、
# 決まり文句の部分が近いという理由で上位に並ぶ
REDACTION_NOTICE = re.compile(
    r"INFORMATION\s+REDACTED\s+PURSUANT\s+TO\s+THE\s+FREEDOM\s+OF\s+INFORMATION\s+ACT\s*\(FOIA\),?"
    r"\s*5\s*U\.S\.C\.?\s*552\(B\)\(6\)\.?", re.IGNORECASE)
REDACTION_MASK = re.compile(r"\[XXX\]|\bXXX\b|\*\*\*")


def remove_redactions(text: str) -> str:
    text = REDACTION_MASK.sub(" ", REDACTION_NOTICE.sub(" ", text))
    return re.sub(r"\s{2,}", " ", text).strip()


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
        for text in make_chunks(remove_redactions(summary or ""), count_tokens):
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
