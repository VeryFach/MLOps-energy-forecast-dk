import argparse
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--max-age-seconds", type=float, default=900)
    args = parser.parse_args()

    if not args.file.is_file():
        raise SystemExit(f"Heartbeat file does not exist: {args.file}")
    age = time.time() - args.file.stat().st_mtime
    if age > args.max_age_seconds:
        raise SystemExit(
            f"Heartbeat is stale: {age:.0f}s old (limit {args.max_age_seconds:.0f}s)"
        )


if __name__ == "__main__":
    main()
