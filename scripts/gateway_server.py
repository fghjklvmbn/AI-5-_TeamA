from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = PROJECT_ROOT / "backend" / "gateway"
sys.path.insert(0, str(GATEWAY_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-file")
    args = parser.parse_args()
    if args.log_file:
        path = Path(args.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        log = path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    uvicorn.run("memorypal_api.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
