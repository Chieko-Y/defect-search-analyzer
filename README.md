# defect-search-analyzer

公開されている不具合データ（NHTSA の苦情データ）を使って、類似の不具合を検索し、傾向を分析するアプリ。

## セットアップ

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## データ取得

```
python src/ingest/nhtsa_fetch.py SUBARU OUTBACK 2026
```

## 検索画面

- **条件で絞り込む**：AI＋人の確認で付けた分類（機能・症状・危険度など）や、VIN から判定したハイブリッド／ガソリンで絞り込む
- **文章で探す（セマンティック検索）**：入力した文と意味が近い苦情を、近い順に並べる。言葉が一致しなくても見つかり、日本語で英語の苦情を探せる（ローカルで動く無料の軽い多言語モデル `paraphrase-multilingual-MiniLM-L12-v2`。テスト用の質問セットでほかのモデルとも比べた：`python src/analysis/eval_search.py`）。絞り込みと組み合わせられる

```
python src/process/build_db.py
python src/process/embed.py      # 文章で探す検索用（初回はモデルのダウンロードあり）
python -m uvicorn api:app --app-dir src/search --port 8000
```

→ http://127.0.0.1:8000/

データ出典: National Highway Traffic Safety Administration (NHTSA)
