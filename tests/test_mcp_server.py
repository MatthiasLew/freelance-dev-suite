"""Tests for local STDIO MCP server for AI coding agents."""

from __future__ import annotations

import io
import json
from pathlib import Path

from packages.mcp.server import FreelanceMcpServer, MCPServer, run_stdio_server
from packages.workspace.manager import WorkspaceManager


def test_mcp_initialize_and_ping(tmp_path: Path) -> None:
    server = MCPServer(workspace_root=tmp_path)

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-agent", "version": "1.0"},
        },
    }
    resp_str = server.handle_message(json.dumps(init_req))
    assert resp_str is not None
    resp = json.loads(resp_str)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "serverInfo" in resp["result"]
    assert resp["result"]["serverInfo"]["name"] == "freelance-dev-suite"

    # Ping
    ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    ping_resp = json.loads(server.handle_message(json.dumps(ping_req)) or "{}")
    assert ping_resp["result"] == {}


def test_mcp_tools_list(tmp_path: Path) -> None:
    server = MCPServer(workspace_root=tmp_path)
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = json.loads(server.handle_message(json.dumps(req)) or "{}")

    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected = {
        "list_jobs",
        "get_job_status",
        "get_requirements",
        "get_scope_changes",
        "get_work_sessions",
        "get_profitability",
        "get_timeline",
        "create_job",
        "check_scope",
    }
    assert expected.issubset(tool_names)


def test_mcp_create_job_and_get_status(tmp_path: Path) -> None:
    server = MCPServer(workspace_root=tmp_path)

    # Call create_job tool
    create_call = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "create_job",
            "arguments": {
                "client": "MCP Client",
                "description": "Integration test job for MCP protocol",
                "budget_pln": 3000.0,
            },
        },
    }
    resp = json.loads(server.handle_message(json.dumps(create_call)) or "{}")
    assert not resp.get("isError", False)
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    job_id = data["job"]["id"]
    assert job_id.startswith("JOB-")

    # Call get_job_status tool
    status_call = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "get_job_status", "arguments": {"job_id": job_id}},
    }
    status_resp = json.loads(server.handle_message(json.dumps(status_call)) or "{}")
    status_data = json.loads(status_resp["result"]["content"][0]["text"])
    assert status_data["job"]["id"] == job_id
    assert status_data["job"]["client"] == "MCP Client"
    assert status_data["job"]["status"] == "LEAD"


def test_mcp_check_scope(tmp_path: Path) -> None:
    server = MCPServer(workspace_root=tmp_path)
    # First create job
    mgr = WorkspaceManager()
    mgr.config.workspace_root = str(tmp_path)
    job = mgr.create_job(client="Scope Client", description="Scope base project")

    scope_call = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "check_scope",
            "arguments": {
                "job_id": job.id,
                "request_text": "Please add a new Stripe payment gateway with webhook processing",
            },
        },
    }
    resp = json.loads(server.handle_message(json.dumps(scope_call)) or "{}")
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["analyzed"] is True
    assert data["scope_change"]["classification"] == "OUT_OF_SCOPE"
    assert data["scope_change"]["suggested_extra_price_pln"] > 0


def test_mcp_unknown_method(tmp_path: Path) -> None:
    server = MCPServer(workspace_root=tmp_path)
    req = {"jsonrpc": "2.0", "id": 99, "method": "unknown/method"}
    resp = json.loads(server.handle_message(json.dumps(req)) or "{}")
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_query_tools_contract(tmp_path: Path) -> None:
    """All MCP read-only query tools must adhere to the structured envelope contract."""
    mgr = WorkspaceManager()
    mgr.config.workspace_root = str(tmp_path)
    job = mgr.create_job(client="DeepClient", description="Deep MCP tools test")
    job_dir = mgr.get_job_dir(job.id)
    assert job_dir is not None

    (job_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (job_dir / "work" / "sessions").mkdir(parents=True, exist_ok=True)

    server = FreelanceMcpServer(workspace_root=tmp_path)

    # get_requirements when not generated vs generated
    req_resp1 = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "get_requirements", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "NOT_GENERATED" in req_resp1["result"]["content"][0]["text"]

    (job_dir / "analysis" / "requirements.json").write_text(
        json.dumps({"job_id": job.id, "title": "Reqs", "requirements": []}), encoding="utf-8"
    )
    req_resp2 = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {"name": "get_requirements", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "specification" in json.loads(req_resp2["result"]["content"][0]["text"])

    # get_scope_changes
    scope_resp = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {"name": "get_scope_changes", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "changes" in json.loads(scope_resp["result"]["content"][0]["text"])

    # get_work_sessions
    work_resp = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {"name": "get_work_sessions", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "sessions" in json.loads(work_resp["result"]["content"][0]["text"])

    # get_profitability
    prof_resp = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 14,
                    "method": "tools/call",
                    "params": {"name": "get_profitability", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "profitability" in json.loads(prof_resp["result"]["content"][0]["text"])

    # get_timeline
    tl_resp = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 15,
                    "method": "tools/call",
                    "params": {"name": "get_timeline", "arguments": {"job_id": job.id}},
                }
            )
        )
        or "{}"
    )
    assert "events" in json.loads(tl_resp["result"]["content"][0]["text"])

    # list_jobs with include_finished
    list_resp = json.loads(
        server.handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 16,
                    "method": "tools/call",
                    "params": {"name": "list_jobs", "arguments": {"include_finished": True}},
                }
            )
        )
        or "{}"
    )
    assert json.loads(list_resp["result"]["content"][0]["text"])["count"] >= 1


def test_mcp_invalid_job_id_and_traversal_rejected(tmp_path: Path) -> None:
    """Job IDs with path traversal attempts or invalid formats must be rejected."""
    server = MCPServer(workspace_root=tmp_path)

    bad_calls = [
        {"job_id": "../../etc/passwd"},
        {"job_id": "JOB-99999"},
        {"job_id": "INVALID-FORMAT"},
        {"job_id": 12345},
    ]

    for bad_args in bad_calls:
        req = {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "get_job_status", "arguments": bad_args},
        }
        resp = json.loads(server.handle_message(json.dumps(req)) or "{}")
        assert "error" in resp
        assert resp["error"]["code"] == -32602


def test_mcp_stdio_server_error_tolerance(tmp_path: Path) -> None:
    """The stdio server loop must handle invalid JSON lines without terminating."""
    in_stream = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        + "\n"
        + "invalid json line\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    )
    out_stream = io.StringIO()
    run_stdio_server(
        workspace_root=tmp_path,
        input_stream=in_stream,
        output_stream=out_stream,
    )
    out_lines = out_stream.getvalue().strip().splitlines()
    assert len(out_lines) == 3
    assert json.loads(out_lines[0])["result"] == {}
    assert "error" in json.loads(out_lines[1])
    assert "tools" in json.loads(out_lines[2])["result"]


def test_mcp_job_id_validation_cases(tmp_path: Path) -> None:
    """Verify strict MCP job ID regex (^JOB-\\d+$) contract and boundary rejection."""
    server = MCPServer(workspace_root=tmp_path)

    # Setup real jobs matching JOB-1 and JOB-0001
    active_dir = tmp_path / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    for j_id in ["JOB-1", "JOB-0001"]:
        j_dir = active_dir / f"{j_id}-test"
        j_dir.mkdir(parents=True, exist_ok=True)
        (j_dir / "job.json").write_text(
            json.dumps({"id": j_id, "client": "TestCo", "description": "Test"}),
            encoding="utf-8",
        )

    # 1. Accepted valid formats
    for valid_id in ["JOB-1", "JOB-0001"]:
        req = {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {"name": "get_job_status", "arguments": {"job_id": valid_id}},
        }
        resp = json.loads(server.handle_message(json.dumps(req)) or "{}")
        err = resp.get("error")
        assert "result" in resp, f"Expected {valid_id} to be accepted, got error: {err}"
        assert "error" not in resp

    # 2. Rejected invalid formats and path traversals
    rejected_cases = [
        "foo",
        "JOB-test",
        "../JOB-1",
        "JOB-1/../../x",
        "/etc/passwd",
        "C:\\Windows\\System32",
        "JOB-",
        "JOB-1; rm -rf /",
    ]
    for bad_id in rejected_cases:
        req = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {"name": "get_job_status", "arguments": {"job_id": bad_id}},
        }
        resp = json.loads(server.handle_message(json.dumps(req)) or "{}")
        assert "error" in resp, f"Expected {bad_id} to be rejected"
        assert resp["error"]["code"] == -32602
        assert "Invalid job ID format" in resp["error"]["message"]
