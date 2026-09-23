"""Add facts that can be decided by data (not by AI): powertrain from VIN, and duplicate complaints.

Usage:
    python src/process/enrich.py

出力: data/processed/rav4_vehicle_info.jsonl（1行1件、odiNumber で分類結果と結びつける）
VIN の解読結果は data/processed/vin_decoded.json に保存し、2回目からは NHTSA に問い合わせない。
"""
import json
import re

import requests

from classify import ROOT, load_complaints

VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
VIN_CACHE = ROOT / "data" / "processed" / "vin_decoded.json"
OUT_PATH = ROOT / "data" / "processed" / "rav4_vehicle_info.jsonl"


def decode_vins(vins: list[str]) -> dict[str, dict]:
    """NHTSA の vPIC API で VIN（先頭11文字）を解読する。一度に50件まで送れる"""
    cache = json.loads(VIN_CACHE.read_text(encoding="utf-8")) if VIN_CACHE.exists() else {}
    todo = [v for v in vins if v not in cache]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        r = requests.post(VPIC_URL, data={"format": "json", "data": ";".join(chunk)}, timeout=60)
        r.raise_for_status()
        for d in r.json()["Results"]:
            cache[d["VIN"]] = {k: d[k] for k in ("Model", "Trim", "FuelTypePrimary", "ElectrificationLevel")}
        print(f"VIN 解読 {min(i + 50, len(todo))}/{len(todo)}")
    VIN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    VIN_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def powertrain(d: dict | None) -> str:
    if not d:
        return "unknown"
    level = d.get("ElectrificationLevel") or ""
    if "PHEV" in level:
        return "plug-in hybrid"
    if "HEV" in level:
        return "hybrid"
    if d.get("FuelTypePrimary") == "Gasoline":
        return "gas"
    return "unknown"


def find_duplicates(rows: list[dict]) -> dict[int, int]:
    """同じ出来事の二重登録を見つけ、{後の苦情: 最初の苦情} を返す

    ルール: VIN（先頭11文字）と事故日が同じ → 同じ車の同じ出来事とみなす。
    VIN の先頭11文字は車1台ごとに違うわけではないが、事故日まで一致すればほぼ同じ車と言える。
    念のため、苦情文の単語が9割以上同じものも重複とする。
    """
    words = {r["odiNumber"]: set(re.findall(r"[a-z0-9]+", (r.get("summary") or "").lower())) for r in rows}
    rows = sorted(rows, key=lambda r: r["odiNumber"])
    dup_of = {}
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if b["odiNumber"] in dup_of:
                continue
            same_event = a.get("vin") and a["vin"] == b.get("vin") and a["dateOfIncident"] == b["dateOfIncident"]
            wa, wb = words[a["odiNumber"]], words[b["odiNumber"]]
            same_text = bool(wa | wb) and len(wa & wb) / len(wa | wb) >= 0.9
            if same_event or same_text:
                dup_of[b["odiNumber"]] = dup_of.get(a["odiNumber"], a["odiNumber"])
    return dup_of


def main() -> None:
    rows = load_complaints()
    decoded = decode_vins(sorted({r["vin"] for r in rows if r.get("vin")}))
    dup_of = find_duplicates(rows)

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for r in rows:
            d = decoded.get(r.get("vin"))
            record = {
                "odiNumber": r["odiNumber"],
                "vin": r.get("vin"),
                "vin_trim": d.get("Trim") if d else None,
                "powertrain_vin": powertrain(d),
                "duplicate_of": dup_of.get(r["odiNumber"]),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = {}
    for r in rows:
        p = powertrain(decoded.get(r.get("vin")))
        counts[p] = counts.get(p, 0) + 1
    print("パワートレイン:", counts)
    print("重複:", {k: v for k, v in sorted(dup_of.items())})
    print("saved:", OUT_PATH)


if __name__ == "__main__":
    main()
