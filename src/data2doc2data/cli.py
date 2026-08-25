"""Command-line interface for local setup and evidence-loop analysis."""

from __future__ import annotations

import argparse
from http import HTTPStatus
import json
from pathlib import Path
import subprocess
import sys
import webbrowser

from .agents.codex import CodexProvider
from .agents.gateway import AgentGateway
from .agents.workbuddy import WorkBuddyProvider
from .analysis import InputValidationError, analyze, load_profile_ruleset
from .artifacts import ArtifactStore
from .config import Profile, ProfileError, ProfileStore, default_store
from .cycle_runner import DemoCycleRunner
from .rules import load_ruleset
from .server import create_server
from .reporting import build_html_report_from_cycle, write_html_report
from .workbench_api import WorkbenchApiError, WorkbenchService
from .workspace_store import WorkspaceStore, WorkspaceStoreError


def main(argv: list[str] | None = None, stdout=None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    store = ProfileStore(Path(args.config)) if args.config else default_store()

    try:
        if args.command == "status":
            profile = store.load()
            print(
                json.dumps({"configured": profile is not None, "mode": profile.mode if profile else None}), file=output
            )
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
        if args.command == "analyze-case":
            from .plugin_service import PluginService

            service = PluginService(store)
            result = service.analyze_business_case(
                args.question,
                args.sources,
                title=args.title,
                rules_path=args.rules,
            )
            artifact = service.workbench.local_task_report(str(result["task_id"]))
            path, digest = write_html_report(artifact, Path(args.output))
            result["report"] = {
                "output": str(path),
                "mime_type": "text/html; charset=utf-8",
                "byte_count": path.stat().st_size,
                "sha256": digest,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2), file=output)
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
        if args.command == "install-mcp":
            executable = Path(sys.executable).parent / "data2doc2data"
            if not executable.is_file():
                raise InputValidationError("data2doc2data must first be installed in the active Python environment")
            command = (
                ["codebuddy", "mcp", "add", "--scope", args.scope, "data2doc2data", "--", str(executable), "mcp"]
                if args.host in {"codebuddy", "workbuddy"}
                else ["codex", "mcp", "add", "data2doc2data", "--", str(executable), "mcp"]
            )
            if args.dry_run:
                print(json.dumps({"host": args.host, "scope": args.scope, "status": "dry_run", "command": command}, ensure_ascii=False), file=output)
                return 0
            try:
                completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
            except FileNotFoundError as error:
                raise InputValidationError(f"{args.host} CLI is unavailable; install it and sign in before registering MCP") from error
            except subprocess.TimeoutExpired as error:
                raise InputValidationError(f"{args.host} MCP registration timed out") from error
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()[:500]
                raise InputValidationError(f"{args.host} MCP registration failed: {detail}")
            print(
                json.dumps(
                    {"host": args.host, "scope": args.scope, "status": "installed", "command": command, "message": completed.stdout.strip()[:500]},
                    ensure_ascii=False,
                ),
                file=output,
            )
            return 0
        if args.command == "report":
            service = WorkbenchService(WorkspaceStore(store.workspace_database_path))
            artifact = service.local_task_report(args.task)
            path, digest = write_html_report(artifact, Path(args.output))
            print(
                json.dumps(
                    {
                        "task_id": args.task,
                        "output": str(path),
                        "mime_type": "text/html; charset=utf-8",
                        "sha256": digest,
                    },
                    ensure_ascii=False,
                ),
                file=output,
            )
            return 0
        if args.command == "cycle-run":
            workspace = WorkspaceStore(store.workspace_database_path)
            task = workspace.get_task(args.task)
            if task is None:
                raise WorkspaceStoreError("task not found")
            result = DemoCycleRunner(workspace).run(
                task,
                Path(args.data),
                tuple(Path(path) for path in args.documents),
            )
            print(
                json.dumps(
                    {"cycle": result.cycle.to_dict(), "artifact_refs": list(result.cycle.artifact_refs)},
                    ensure_ascii=False,
                ),
                file=output,
            )
            return 0
        if args.command == "cycle-artifacts":
            workspace = WorkspaceStore(store.workspace_database_path)
            cycle = workspace.get_analysis_cycle(args.cycle)
            if cycle is None:
                raise WorkspaceStoreError("analysis cycle not found")
            print(
                json.dumps({"cycle_id": cycle.cycle_id, "artifact_refs": list(cycle.artifact_refs)}, ensure_ascii=False),
                file=output,
            )
            return 0
        if args.command == "cycle-report":
            workspace = WorkspaceStore(store.workspace_database_path)
            cycle = workspace.get_analysis_cycle(args.cycle)
            if cycle is None:
                raise WorkspaceStoreError("analysis cycle not found")
            context = workspace.get_analysis_cycle_context(cycle.cycle_id)
            task = workspace.get_task(str(context.get("task_id", "")))
            if task is None:
                raise WorkspaceStoreError("analysis cycle task not found")
            artifact = build_html_report_from_cycle(
                task,
                cycle,
                ArtifactStore(workspace.path.parent / "artifacts"),
                run_count=len(workspace.list_runs(task.task_id)),
            )
            path, digest = write_html_report(artifact, Path(args.output))
            print(
                json.dumps({"cycle_id": cycle.cycle_id, "output": str(path), "sha256": digest}, ensure_ascii=False),
                file=output,
            )
            return 0
        return _run_setup(store, args.port, args.no_browser, output)
    except (InputValidationError, ProfileError, WorkspaceStoreError, WorkbenchApiError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=output)
        return 4 if isinstance(error, WorkbenchApiError) and error.status == HTTPStatus.NOT_FOUND else 2


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
    business_case = commands.add_parser("analyze-case", help="Analyze local business materials and deliver HTML without a task ID.")
    business_case.add_argument("--question", required=True, help="Business question to answer.")
    business_case.add_argument("--source", dest="sources", action="append", required=True, help="Local source directory or file; repeat for multiple materials.")
    business_case.add_argument("--output", required=True, help="Destination standalone HTML report.")
    business_case.add_argument("--title", help="Optional analysis task title.")
    business_case.add_argument("--rules", help="Optional declarative rules JSON file.")

    check_rules = commands.add_parser("check-rules", help="Validate a declarative rules JSON file.")
    check_rules.add_argument("--rules", required=True, help="Path to the rules JSON file.")

    commands.add_parser("mcp", help="Run the MCP stdio tool server for cross-harness tool calls.")
    doctor = commands.add_parser("doctor", help="Verify cases, MCP tools, and host templates without spawning agents.")
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable diagnostic report.")
    install = commands.add_parser("install-mcp", help="Register this Python environment's MCP server with a local host.")
    install.add_argument("--host", required=True, choices=("codebuddy", "workbuddy", "codex"), help="Local MCP-capable host CLI.")
    install.add_argument("--scope", default="user", choices=("local", "project", "user"), help="CodeBuddy registration scope.")
    install.add_argument("--dry-run", action="store_true", help="Print the exact registration command without changing the host.")
    report = commands.add_parser("report", help="Generate a standalone HTML report for a workbench task.")
    report.add_argument("--task", required=True, help="Workbench task ID.")
    report.add_argument("--output", required=True, help="Destination .html file.")
    cycle_run = commands.add_parser("cycle-run", help="Run a persisted model-free local analysis cycle.")
    cycle_run.add_argument("--task", required=True, help="Workbench task ID.")
    cycle_run.add_argument("--data", required=True, help="Local analytical CSV path.")
    cycle_run.add_argument("--documents", nargs="*", default=[], help="Optional local document paths.")
    cycle_artifacts = commands.add_parser("cycle-artifacts", help="List opaque artifact IDs for a cycle.")
    cycle_artifacts.add_argument("--cycle", required=True, help="Analysis cycle ID.")
    cycle_report = commands.add_parser("cycle-report", help="Generate a standalone report from a persisted cycle.")
    cycle_report.add_argument("--cycle", required=True, help="Analysis cycle ID.")
    cycle_report.add_argument("--output", required=True, help="Destination .html file.")
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
