"""Command-line interface for local setup and evidence-loop analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from .analysis import InputValidationError, analyze
from .config import Profile, ProfileError, ProfileStore, default_store
from .server import create_server


def main(argv: list[str] | None = None, stdout=None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    store = ProfileStore(Path(args.config)) if args.config else default_store()

    try:
        if args.command == "status":
            profile = store.load()
            print(json.dumps({"configured": profile is not None, "mode": profile.mode if profile else None}), file=output)
            return 0
        if args.command == "analyze":
            result = analyze(args.question, store.load() or Profile.demo(), args.metric_override)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), file=output)
            return 0
        return _run_setup(store, args.port, args.no_browser, output)
    except (InputValidationError, ProfileError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=output)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Data-to-Doc-to-Data evidence loops.")
    parser.add_argument("--config", help="Local profile path. Defaults to ~/.config/data2doc2data/config.json")
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="Open the local configuration page.")
    setup.add_argument("--port", type=int, default=8765)
    setup.add_argument("--no-browser", action="store_true")

    analyze_parser = commands.add_parser("analyze", help="Analyze the saved profile or built-in demo.")
    analyze_parser.add_argument("--question", required=True)
    analyze_parser.add_argument("--metric", dest="metric_override", help="Optional exact metric name override.")

    commands.add_parser("status", help="Print whether a local profile is configured.")
    return parser


def _run_setup(store: ProfileStore, port: int, no_browser: bool, output) -> int:
    server = create_server(store, port=port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Data2Doc2Data setup is available at {url}", file=output)
    if not no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
