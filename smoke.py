#!/usr/bin/env python3
# Eclipse Dispatch MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Eclipse Dispatch v0.1 — end-to-end stdio smoke: real subprocess,

"""Eclipse Dispatch v0.1 — end-to-end stdio smoke: real subprocess,
temp state, fixture adapters. Draft -> preview -> approve -> syndicate
-> analytics -> receipts. Nothing leaves this machine."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent


def call(proc, rid, name, args):
    req = {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
           "params": {"name": name, "arguments": args}}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    resp = json.loads(proc.stdout.readline())
    out = json.loads(resp["result"]["content"][0]["text"])
    assert "error" not in out, f"{name} errored: {out}"
    return out


def main():
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, ECLIPSE_DISPATCH_STATE=str(Path(td) / "state.json"))
        proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                text=True, env=env)
        try:
            init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26"}}
            proc.stdin.write(json.dumps(init) + "\n")
            proc.stdin.flush()
            hello = json.loads(proc.stdout.readline())
            assert hello["result"]["serverInfo"]["name"] == "eclipse-dispatch"

            d = call(proc, 1, "draft_create", {
                "title": "Smoke Dispatch: The Week Everything Drafted",
                "subtitle": "A stdio smoke in three acts",
                "body": "Act one: a draft exists.\n\nAct two: it is approved.\n\nAct three: it is everywhere, as drafts.",
                "canonical_url": "https://fixture.example.com/articles/smoke",
                "tags": ["smoke"], "audience": "free"})
            print("draft:", d["draft_id"], "v", d["version"], d["content_hash"][:12])
            prev = call(proc, 2, "draft_preview", {"draft_id": d["draft_id"]})
            print("preview platforms:", sorted(prev["previews"]))
            appr = call(proc, 3, "draft_approve", {"draft_id": d["draft_id"]})
            syn = call(proc, 4, "syndicate_drafts", {
                "draft_id": d["draft_id"],
                "approval_token": appr["approval_token"]})
            for r in syn["results"]:
                print("syndicated:", r["platform"], r["mode"],
                      r.get("remote_status"))
            rep = call(proc, 5, "analytics_report", {})
            print("analytics metrics:", sorted(rep["metrics"]),
                  "| open_rate combined:", rep["metrics"]["open_rate"]["combined"],
                  "| flag:", rep["metrics"]["open_rate"]["flag"][:30])
            rec = call(proc, 6, "receipt_list", {})
            print("receipts:", rec["count"], "chain_valid:", rec["chain_valid"])
            assert rec["chain_valid"]
        finally:
            proc.terminate()
    print("SMOKE OK")


if __name__ == "__main__":
    main()

# Eclipse Dispatch MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
