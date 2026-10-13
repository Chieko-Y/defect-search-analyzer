"""Keyword scoring (BM25) and combining it with the meaning-based ranking (RRF).

意味の近さだけで並べると、「water leak」で本文が「Oil leak」だけの苦情が1位になる、
「Android Auto」で「automatically」の苦情が上に来る、のように、言葉が合っていないものが上に来る。
そこで、言葉が合っているかの順位も作り、2つの順位を組み合わせる（ハイブリッド検索）。

- BM25: よく使われるキーワード検索の点数。めずらしい言葉（water）が合うほど高く、
  どこにでもある言葉（car）が合ってもあまり上がらない。長い苦情ほど少し割り引く
- RRF（Reciprocal Rank Fusion）: 点数ではなく順位を組み合わせる。意味の近さ（0.8 台）と
  BM25（0〜十数点）は点数の幅がまったく違うので、そのまま足せないため

2026-10-13 に質問セットで比べた結果、キーワードは短い言い方でしか効かず、文章で探したときは
変わらなかった。あいまいな文章でも意味から探すセマンティック検索にしたいので、アプリでは使わない。
比べた記録として、src/analysis/eval_search.py から使う。
"""
import math
import re
from collections import Counter

import snowballstemmer

# どの苦情にもよく出てきて、探す手がかりにならない言葉
STOP_WORDS = set("""
a an the and or but if of to in on at by for with from as is are was were be been being it its this that
these those i my me we our you your he she they them his her their there here not no so than then too very
can could would should will just have has had do does did when while after before about into out up down
over again also only such what which who whom how all any some
""".split())

_stemmer = snowballstemmer.stemmer("english")


def tokenize(text: str) -> list[str]:
    """英語の単語に分け、形をそろえる（leaking / leaked / leaks → leak）

    日本語の文字は拾わないので、日本語で探したときはキーワードの点数は付かない
    """
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS and len(w) > 1]
    return _stemmer.stemWords(words)


class KeywordIndex:
    """苦情ごとの BM25 の点数を出す（苦情文を分けた部分ではなく、苦情全体で数える）"""

    K1 = 1.5   # 同じ言葉が何回も出てきたときに、どこまで点数を上げるか
    B = 0.75   # 長い苦情をどのくらい割り引くか

    def __init__(self, docs: dict[int, str]):
        self.counts = {odi: Counter(tokenize(text)) for odi, text in docs.items()}
        self.lengths = {odi: sum(c.values()) for odi, c in self.counts.items()}
        self.avg_length = sum(self.lengths.values()) / max(len(self.lengths), 1)
        doc_freq = Counter(word for c in self.counts.values() for word in c)
        n = len(self.counts)
        self.idf = {word: math.log(1 + (n - df + 0.5) / (df + 0.5)) for word, df in doc_freq.items()}

    def scores(self, q: str, odi_numbers: set[int]) -> dict[int, float]:
        """q の言葉が1つでも入っている苦情だけを返す → {番号: 点数}"""
        words = [w for w in set(tokenize(q)) if w in self.idf]
        result = {}
        for odi in odi_numbers:
            counts = self.counts.get(odi)
            if not counts:
                continue
            norm = self.K1 * (1 - self.B + self.B * self.lengths[odi] / self.avg_length)
            score = sum(self.idf[w] * counts[w] * (self.K1 + 1) / (counts[w] + norm) for w in words if w in counts)
            if score > 0:
                result[odi] = score
        return result


RRF_K = 60  # 順位の差をどのくらいならすか（論文で使われた値。よく使われる）


def fuse(*rankings: list[int]) -> list[int]:
    """いくつかの順位を組み合わせる。どの順位でも上にあるものほど上に来る

    どれかの順位に出てこない苦情は、その順位からは点数をもらえない
    """
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, odi in enumerate(ranking, start=1):
            score[odi] = score.get(odi, 0.0) + 1 / (RRF_K + rank)
    return sorted(score, key=lambda odi: -score[odi])
