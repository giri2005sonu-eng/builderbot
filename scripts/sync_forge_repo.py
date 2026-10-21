#!/usr/bin/env python3
"""Sync the FORGE repo into this builderbot repository.

This script clones the public source repository from GitHub and copies its tracked files
into a local folder inside the current repository so it can be reviewed and modified here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_REPO = "https://github.com/jaiprakashyadav120820052005-crypto/FORGE.git"
TARGET_DIR = Path(__file__).resolve().parents[1] / "vendor" / "FORGE"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    if TARGET_DIR.exists():
        print(f"Target already exists: {TARGET_DIR}")
        print("Removing existing copy to refresh it...")
        shutil.rmtree(TARGET_DIR)

    TARGET_DIR.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="forge_sync_") as tmp:
        tmp_path = Path(tmp)
        cloned = tmp_path / "FORGE"
        print(f"Cloning {SOURCE_REPO} ...")
        run(["git", "clone", "--depth", "1", SOURCE_REPO, str(cloned)])

        print(f"Copying repo contents into {TARGET_DIR} ...")
        shutil.copytree(cloned, TARGET_DIR, dirs_exist_ok=False)

    print(f"Done. Files synced into: {TARGET_DIR}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Sync failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
