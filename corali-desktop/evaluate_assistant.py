"""Run synthetic document cases locally; retain raw answers for human review.

Use a separate data directory containing the pinned AI runtime and model.
Does not download, train, apply answers, or read personal documents.
"""

import argparse
import importlib.util
import json
import threading
import time
from pathlib import Path

from local_ai import LocalAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation", type=Path)
    parser.add_argument("--arch", choices=("arm64", "x64"), required=True)
    parser.add_argument("--profile", choices=("light", "capable"), default="light")
    parser.add_argument("--cases", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    implementation = LocalAI
    if args.implementation:
        spec = importlib.util.spec_from_file_location(
            "baseline_local_ai", args.implementation
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        implementation = module.LocalAI
    args.data = args.data.resolve()
    ai = implementation(
        args.data,
        root / "ai-manifest.json",
        args.data / "no-pack",
        architecture=args.arch,
    )
    if hasattr(ai, "configure"):
        ai.configure(
            {
                "enabled": True,
                "preload": False,
                "profile": args.profile,
                "idleMinutes": 1,
            }
        )
    original_open = ai.http.open

    def fixed_seed(request, *a, **kw):
        if request.full_url.endswith("/v1/chat/completions"):
            payload = json.loads(request.data)
            payload["seed"] = 42
            request.data = json.dumps(payload).encode()
        return original_open(request, *a, **kw)

    ai.http.open = fixed_seed
    dataset = json.loads(
        (args.cases or root / "evaluation/assistant-cases.json").read_text("utf8")
    )
    report = {
        "scope": dataset["scope"],
        "architecture": args.arch,
        "model": (
            ai.model_spec()[1] if hasattr(ai, "model_spec") else ai.manifest["model"]
        ),
        "seed": 42,
        "source": dataset["source"],
        "answers": [],
        "automaticPassRate": None,
        "humanReviewRequired": True,
    }
    try:
        for case in dataset["cases"]:
            start = time.monotonic()
            answer = ai.ask(
                case["prompt"], case["context"], "documenti", threading.Event()
            )
            report["answers"].append(
                {
                    **case,
                    "answer": answer["text"],
                    "seconds": round(time.monotonic() - start, 3),
                    "incomplete": answer["incomplete"],
                }
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
            )
            print(case["id"] + " completed", flush=True)
    finally:
        ai.stop()


if __name__ == "__main__":
    main()
