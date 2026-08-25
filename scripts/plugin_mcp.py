"""Launch the plugin's own installed environment without trusting global PATH."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for relative in (".venv/bin/data2doc2data", ".venv/Scripts/data2doc2data.exe"):
        executable = root / relative
        if executable.is_file() and os.access(executable, os.X_OK):
            os.execv(str(executable), [str(executable), "mcp"])

    if importlib.util.find_spec("data2doc2data") is not None:
        os.execv(sys.executable, [sys.executable, "-m", "data2doc2data.cli", "mcp"])

    print(
        "Data2Doc2Data plugin runtime is not installed. In the plugin directory, run: "
        "python3 -m venv .venv && .venv/bin/python -m pip install -e .",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
