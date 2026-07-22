from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memorypal_api.worker import main as run_worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file")
    args = parser.parse_args()
    if args.log_file:
        path = Path(args.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        log = path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    run_worker()


if __name__ == "__main__":
    main()
