import json
from pathlib import Path
import sys
import time


if "--version" in sys.argv:
    print("codex-cli 0.148.0")
    raise SystemExit(0)

fixture = Path(__file__).with_name("turn.jsonl")
crash_on_turn = "--crash-on-turn" in sys.argv
hang_on_initialize = "--hang-on-initialize" in sys.argv
delay_turn_events = "--delay-turn-events" in sys.argv

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        if hang_on_initialize:
            continue
        response = {"id": request_id, "result": {"userAgent": "fake-codex"}}
    elif method in {"thread/start", "thread/resume"}:
        if "runtimeWorkspaceRoots" in request.get("params", {}):
            response = {
                "id": request_id,
                "error": {"code": -32600, "message": "runtimeWorkspaceRoots requires experimentalApi capability"},
            }
        else:
            response = {"id": request_id, "result": {"thread": {"id": "thread-1"}}}
    elif method == "turn/start":
        if "runtimeWorkspaceRoots" in request.get("params", {}):
            response = {
                "id": request_id,
                "error": {"code": -32600, "message": "runtimeWorkspaceRoots requires experimentalApi capability"},
            }
        else:
            response = {"id": request_id, "result": {"turn": {"id": "turn-1"}}}
    elif method == "turn/interrupt":
        response = {"id": request_id, "result": {}}
    elif request_id == 900:
        continue
    else:
        continue
    print(json.dumps(response), flush=True)
    if method == "turn/start":
        if crash_on_turn:
            raise SystemExit(7)
        if delay_turn_events:
            time.sleep(0.1)
        workspace = request["params"]["cwd"]
        for event_line in fixture.read_text(encoding="utf-8").splitlines():
            event = json.loads(event_line.replace("WORKSPACE", workspace))
            print(json.dumps(event), flush=True)
