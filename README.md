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

```
python src/process/build_db.py
python -m uvicorn api:app --app-dir src/search --port 8000
```

→ http://127.0.0.1:8000/

データ出典: National Highway Traffic Safety Administration (NHTSA)
