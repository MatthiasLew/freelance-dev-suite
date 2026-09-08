"""Validate that a release tag and package metadata describe the same version."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", args.tag)
    if match is None:
        raise SystemExit(f"Release tag must use vMAJOR.MINOR.PATCH: {args.tag}")
    with Path("pyproject.toml").open("rb") as handle:
        package_version = str(tomllib.load(handle)["project"]["version"])
    if match.group(1) != package_version:
        raise SystemExit(
            f"Tag version {match.group(1)} does not match package version {package_version}"
        )
    print(f"Release metadata is consistent for {package_version}.")


if __name__ == "__main__":
    main()
