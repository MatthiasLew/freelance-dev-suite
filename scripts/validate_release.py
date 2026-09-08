"""Validate that a release tag and package metadata describe the same version."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def _package_version() -> str:
    with Path("pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)
    configured = metadata["project"].get("version")
    if configured is not None:
        return str(configured)

    version_path = Path(metadata["tool"]["hatch"]["version"]["path"])
    match = re.search(
        r'^__version__\s*=\s*["\'](?P<version>[^"\']+)["\']',
        version_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise SystemExit(f"Could not read __version__ from {version_path}")
    return match.group("version")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", args.tag)
    if match is None:
        raise SystemExit(f"Release tag must use vMAJOR.MINOR.PATCH: {args.tag}")
    package_version = _package_version()
    if match.group(1) != package_version:
        raise SystemExit(
            f"Tag version {match.group(1)} does not match package version {package_version}"
        )
    print(f"Release metadata is consistent for {package_version}.")


if __name__ == "__main__":
    main()
