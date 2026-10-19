# defect-search-analyzer

[English version](README.md)

NHTSA（アメリカ運輸省道路交通安全局）が公開している車の苦情データを使って、似た不具合を検索し、不具合の傾向を分析する Web アプリです。

いまのデータは、トヨタ RAV4（2022〜2025年式）の持ち主からの苦情 555件です。

作った背景や設計の理由は、[設計書](docs/design.md)を見てください。

## できること

### 検索の画面（`/`）

- **分類で絞り込む**：機能・症状・危険度などの分類や、ハイブリッド／ガソリン（VIN から判定）で苦情を絞り込みます
- **文章で探す（セマンティック検索）**：入力した文と意味が近い苦情を、近い順に並べます。言葉が一致しなくても見つかり、英語の苦情を日本語で探すこともできます。絞り込みと組み合わせられます
- **詳細の画面**：1件の苦情の元の文と、その分類をあわせて表示します

### 分析の画面（`/analysis`）

A〜E の5つのグラフがあります。棒や点をクリックすると、その条件で絞り込んだ検索の画面が開くので、数字の裏にある実際の苦情を読むことができます。

- **A.** 苦情が多いのは、どの機能・どの症状か
- **B.** いちばん危険な苦情（危険度3）は、何についてのものか
- **C.** 危険度2の苦情は、走行中か停車中か
- **D.** ハイブリッド車とガソリン車で違いはあるか
- **E.** 新しい年式で、増えた問題・なくなった問題はあるか

どのグラフにも、何件の中での割合なのかを書いています。

## しくみ

```
NHTSA の苦情 API
  → src/ingest/nhtsa_fetch.py     苦情を取得する
  → src/process/classify.py       苦情を1件ずつ分類する（ルール：docs/classification_spec.md）
  → src/process/enrich.py         VIN からハイブリッド／ガソリンを判定し、重複を調べる（AI ではなくデータで決める）
  → src/process/build_db.py       すべてを SQLite（defects.db）に入れる
  → src/process/embed.py          セマンティック検索のために、苦情文をベクトルにする
  → src/search/api.py + web/      検索と分析の画面
```

- 分類のルールは、一部の苦情を自分の手で分類して AI の結果と比べながら、何度か直してきました（いまは v7）。詳しくは [`docs/classification_spec.md`](docs/classification_spec.md) にあります。
- セマンティック検索には、ローカルで無料で動く小さな多言語モデル（`paraphrase-multilingual-MiniLM-L12-v2`）を使っています。モデルや検索の設定は、テスト用の質問セット（`data/eval/search_queries.json`、`src/analysis/eval_search.py`）で比べて決めました。
- 分類の結果は `data/processed/` に入っているので、アプリを動かすときに有料の AI の API は使いません。

## 使っている技術

Python、FastAPI、SQLite、sentence-transformers、HTML / JavaScript、Chart.js

## 準備と起動（Windows）

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python src/process/build_db.py
python src/process/embed.py      # 初回はモデルのダウンロードがあります
python -m uvicorn api:app --app-dir src/search --port 8000
```

起動したら http://localhost:8000/ を開きます。サーバーは最初にモデルを読み込むので、起動まで10秒〜1分ほどかかります。

## データの出典

National Highway Traffic Safety Administration（NHTSA）の Complaints API。
苦情は車の持ち主が送ったもので、NHTSA が内容を確かめたものではありません。このアプリの割合は「送られた苦情の中での割合」で、不具合の発生率ではありません。
