"""Command-line interface for local setup and evidence-loop analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from .agents.codex import CodexProvider
from .agents.gateway import AgentGateway
from .agents.workbuddy import WorkBuddyProvider
from .analysis import InputValidationError, analyze, load_profile_ruleset
from .config import Profile, ProfileError, ProfileStore, default_store
from .rules import load_ruleset
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
            profile = store.load() or Profile.demo()
            ruleset = load_ruleset(Path(args.rules)) if args.rules else load_profile_ruleset(profile)
            result = analyze(
                args.question,
                profile,
                args.metric_override,
                store.index_cache_path,
                ruleset,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), file=output)
            return 0
        if args.command == "check-rules":
            ruleset = load_ruleset(Path(args.rules))
            summary = {
                "valid": True,
                "metrics": sorted(ruleset.metrics),
                "rules": [rule.rule_id for rule in ruleset.rules],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2), file=output)
            return 0
        if args.command == "mcp":
            from .mcp_server import serve

            serve(store)
            return 0
        if args.command == "doctor":
            from .integrations import run_doctor

            report = run_doctor(store)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2), file=output)
            else:
                status = "PASS" if report["ok"] else "FAIL"
                print(f"Data2Doc2Data integration doctor: {status}", file=output)
                for check in report["checks"]:
                    print(f"- {check['id']}: {'ok' if check['ok'] else 'failed'}", file=output)
            return 0 if report["ok"] else 1
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
    analyze_parser.add_argument("--rules", help="Optional declarative rules JSON file.")

    check_rules = commands.add_parser("check-rules", help="Validate a declarative rules JSON file.")
    check_rules.add_argument("--rules", required=True, help="Path to the rules JSON file.")

    commands.add_parser("mcp", help="Run the MCP stdio tool server for cross-harness tool calls.")
    doctor = commands.add_parser("doctor", help="Verify cases, MCP tools, and host templates without spawning agents.")
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable diagnostic report.")
    commands.add_parser("status", help="Print whether a local profile is configured.")
    return parser


def _run_setup(store: ProfileStore, port: int, no_browser: bool, output) -> int:
    workspace = Path.cwd().resolve()
    gateway = AgentGateway(
        {
            "codex": CodexProvider(workspace),
            "workbuddy": WorkBuddyProvider(workspace),
        }
    )
    server = create_server(store, port=port, gateway=gateway, agent_workspace=workspace)
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
