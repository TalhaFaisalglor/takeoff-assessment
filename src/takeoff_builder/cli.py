from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI Takeoff Builder Challenge prototype.")
    parser.add_argument(
        "--root",
        default=".",
        help="Workspace root containing the assessment dataset.",
    )
    parser.add_argument(
        "--output",
        default="artifacts",
        help="Directory where manifests, predictions, and reports will be written.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    summary = run_pipeline(root, output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
