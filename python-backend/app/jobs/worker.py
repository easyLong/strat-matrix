"""Compatibility imports and explicit diagnostics; no standalone poller."""
import argparse
import json
import logging
from .handlers import JOBS, execute, run_once


def main():
    parser = argparse.ArgumentParser(description="Background execution is now part of FastAPI")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.once:
        parser.error("Start the Python API; Java triggers execution. Use --once only for diagnostics.")
    logging.basicConfig(level=logging.INFO)
    report = run_once()
    print(json.dumps(report, ensure_ascii=True, default=str))
    return int(any(result["status"] == "failed" for result in report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
