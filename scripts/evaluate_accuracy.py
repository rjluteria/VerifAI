"""Optional live-model regression runner; expected labels are read before review."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from verifai.engine import classify
from verifai.model import Models

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dataset", type=Path, default=ROOT / "evaluations/evidence.json")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if not os.getenv("NVIDIA_API_KEY"):
    parser.error("Set NVIDIA_API_KEY locally; never include it in the report.")
if args.output.exists():
    parser.error("Output exists; preserve previous runs and choose a new path.")
raw = args.dataset.read_bytes()
cases = json.loads(raw)
models = Models()


def run(case):
    started = time.monotonic()
    result = classify(models, case["claim"], case["evidence"])
    return {
        **case,
        "result": result,
        "correct": result["label"] == case["expected"],
        "quotation_provenance": all(q in case["evidence"] for q in result["quotes"]),
        "quotation_relevance": (
            case["required_quote"] in result["quotes"]
            and not any(q in result["quotes"] for q in case.get("excluded_quotes", []))
            if "required_quote" in case
            else None
        ),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


rows = []
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for row in pool.map(run, cases):
        rows.append(row)
        args.output.write_text(
            json.dumps(
                {
                    "scope": "Supplied evidence classification; not extraction, live discovery, browser access or semantic quotation accuracy",
                    "dataset_sha256": hashlib.sha256(raw).hexdigest(),
                    "models": models.names,
                    "correct": sum(r["correct"] for r in rows),
                    "total": len(rows),
                    "results": rows,
                },
                indent=2,
            )
        )
        print(row["id"], row["result"]["label"], row["correct"], flush=True)
raise SystemExit(
    0
    if all(
        r["correct"]
        and r["quotation_provenance"]
        and r["quotation_relevance"] is not False
        for r in rows
    )
    else 1
)
