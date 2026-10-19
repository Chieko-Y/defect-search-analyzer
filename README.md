# defect-search-analyzer

[日本語版はこちら](README.ja.md)

A web app that searches for similar defects and analyzes defect trends, built on public vehicle complaint data from NHTSA (the U.S. National Highway Traffic Safety Administration).

The current dataset is 555 owner complaints about the Toyota RAV4 (model years 2022–2025).

For the background and the reasons behind the design, see the [design document](docs/design.en.md).

## Features

### Search (`/`)

- **Filter by classification**: narrow down complaints by function, symptom, safety impact, and other categories, or by hybrid / gas (decided from each vehicle's VIN)
- **Search by meaning (semantic search)**: type a sentence, and complaints with a similar meaning are listed from closest to farthest. It finds matches even when the words differ, and you can search the English complaints in Japanese. It can be combined with the filters
- **Detail page**: shows one complaint's original text together with its classification

### Analysis (`/analysis`)

Five charts, A to E. Clicking a bar or point opens the search page filtered to that condition, so you can read the actual complaints behind each number.

- **A.** Which functions and symptoms get the most complaints?
- **B.** What are the most dangerous complaints (safety impact 3) about?
- **C.** Safety impact 2: was the car moving or stopped?
- **D.** Do hybrid and gas cars differ?
- **E.** Did a problem appear or go away in a newer model year?

Each chart states how many complaints its percentages are based on.

## How it works

```
NHTSA complaints API
  → src/ingest/nhtsa_fetch.py     fetch complaints
  → src/process/classify.py       classify each complaint (rules: docs/classification_spec.md)
  → src/process/enrich.py         hybrid / gas from the VIN, duplicate check (decided by data, not AI)
  → src/process/build_db.py       load everything into SQLite (defects.db)
  → src/process/embed.py          turn complaint text into vectors for semantic search
  → src/search/api.py + web/      search and analysis pages
```

- The classification rules were refined over several versions (now v7) by comparing the AI's results with my own manual classification of sample complaints. See [`docs/classification_spec.md`](docs/classification_spec.md) (in Japanese).
- Semantic search uses a small multilingual model that runs locally for free (`paraphrase-multilingual-MiniLM-L12-v2`). Models and search settings were compared using a test query set (`data/eval/search_queries.json`, `src/analysis/eval_search.py`).
- The classification results are already included in `data/processed/`, so the app runs without calling any paid AI API.

## Tech stack

Python, FastAPI, SQLite, sentence-transformers, HTML / JavaScript, Chart.js

## Setup and run (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python src/process/build_db.py
python src/process/embed.py      # the first run downloads the model
python -m uvicorn api:app --app-dir src/search --port 8000
```

Then open http://localhost:8000/ . The server takes from 10 seconds to about a minute to start, because it loads the model first.

## Data source

National Highway Traffic Safety Administration (NHTSA), Complaints API.
Complaints are reports submitted by vehicle owners and have not been verified by NHTSA. The percentages in this app are shares among the complaints filed, not defect rates.
