"""Build and smoke-test the wheel in an isolated virtual environment."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, check=True, env=env)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    build = root / "build"
    for p in (dist, build):
        if p.exists():
            import shutil

            shutil.rmtree(p, ignore_errors=True)
    run(sys.executable, "-m", "build", "--outdir", str(dist), str(root))
    wheels = sorted(dist.glob("freelance_dev_suite-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected exactly one wheel, found {len(wheels)}")

    with tempfile.TemporaryDirectory(prefix="freelance-wheel-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        executable = environment / ("Scripts/freelance.exe" if os.name == "nt" else "bin/freelance")
        run(str(python), "-m", "pip", "install", str(wheels[0]))
        run(str(python), "-c", "import freelance_cli, packages")
        run(str(executable), "--help")


if __name__ == "__main__":
    main()
