"""Validate the corpus and print counts only. Does not connect to PostgreSQL."""

import argparse
import json
import sys
from pathlib import Path

from app.services.dataset import (
    DEFAULT_DATASET_PATH,
    DatasetValidationError,
    dataset_summary,
    load_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATASET_PATH)
    arguments = parser.parse_args()
    try:
        cases = load_dataset(arguments.path)
    except DatasetValidationError as error:
        print(f"Dataset invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps(dataset_summary(cases), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
