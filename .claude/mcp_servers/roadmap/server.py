#!/usr/bin/env python3
"""Minimal MCP server exposing get_next_step over stdio.

Wraps .claude/skills/roadmap-next-step/find_next.py so the resolver logic stays
in one place. The script is invoked as a subprocess for each tool call; the
output becomes the text content of the MCP tool response.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "roadmap"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "roadmap-next-step"
    / "find_next.py"
)

TOOL_DEF = {
    "name": "get_next_step",
    "description": (
        "Resolve and return the next roadmap step file from dev_roadmap/. "
        "Returns the absolute path and full contents of the in_progress step "
        "if one exists, otherwise the smallest-numbered pending step. Returns "
        "the literal text 'ROADMAP_COMPLETE' when no steps remain."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def run_next_step() -> tuple[str, bool]:
    proc = subprocess.run(
        ["python3", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or f"find_next.py exited {proc.returncode}"
        return msg, True
    return proc.stdout, False


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def handle(message: dict) -> dict | None:
    method = message.get("method")
    msg_id = message.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": [TOOL_DEF]},
        }
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if name != "get_next_step":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"unknown tool: {name}"},
            }
        text, is_error = run_next_step()
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        }
    if method and method.startswith("notifications/"):
        return None
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return None


def main() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"mcp parse error: {exc}", file=sys.stderr)
            continue
        response = handle(message)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
