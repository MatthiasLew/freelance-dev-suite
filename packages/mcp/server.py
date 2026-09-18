"""Local STDIO MCP server for Freelance Dev Suite business workflow layer."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from freelance_cli import __version__
from freelance_cli.config import load_config
from packages.requirements.models import RequirementsSpec
from packages.scope.detector import ScopeChangeDetector
from packages.security.secrets import assert_safe_path, mask_text
from packages.storage_utils import safe_read_json, storage_lock
from packages.timeline.manager import TimelineManager
from packages.tracking.profitability import ProfitabilityCalculator
from packages.work.storage import list_work_sessions
from packages.workspace.manager import WorkspaceManager
from packages.workspace.storage import load_job

MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "freelance-dev-suite"
SERVER_INSTRUCTIONS = (
    "Freelance Dev Suite business workflow tools. Use list_jobs and get_job_status first. "
    "All operations are strictly bounded to the local workspace; no repository code is scanned "
    "or transmitted. Technical engine operations belong to ai-dev."
)

JsonObject = dict[str, Any]
ToolHandler = Callable[[JsonObject], JsonObject]


class ToolInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    input_schema: JsonObject
    handler: ToolHandler

    def descriptor(self) -> JsonObject:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def _rpc_error(request_id: object, code: int, message: str) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class FreelanceMcpServer:
    def __init__(self, workspace_root: Path | None = None) -> None:
        cfg = load_config()
        if workspace_root:
            cfg.workspace_root = str(workspace_root.resolve())
        self.manager = WorkspaceManager(config=cfg)
        self.workspace_root = self.manager.config.workspace_path
        self._tools = {tool.name: tool for tool in self._build_tools()}

    def handle(self, message: object) -> JsonObject | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "Invalid Request")
        request_id = message.get("id")
        is_notification = "id" not in message
        method = message.get("method")
        if not isinstance(method, str):
            return None if is_notification else _rpc_error(request_id, -32600, "Invalid Request")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return None if is_notification else _rpc_error(request_id, -32602, "Invalid params")

        try:
            result = self._dispatch(method, params)
        except ToolInputError as exc:
            if is_notification:
                return None
            return _rpc_error(request_id, -32602, mask_text(str(exc)))
        except Exception as exc:
            if is_notification:
                return None
            return _rpc_error(request_id, -32603, f"Internal error: {mask_text(str(exc))}")

        if is_notification:
            return None
        if result is None:
            return _rpc_error(request_id, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def handle_message(self, message_str: str) -> str | None:
        try:
            parsed = json.loads(message_str)
        except json.JSONDecodeError:
            return json.dumps(_rpc_error(None, -32700, "Parse error"))
        resp = self.handle(parsed)
        return json.dumps(resp, ensure_ascii=False) if resp is not None else None

    def _dispatch(self, method: str, params: JsonObject) -> JsonObject | None:
        if method == "initialize":
            return {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
                "instructions": SERVER_INSTRUCTIONS,
            }
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool.descriptor() for tool in self._tools.values()]}
        if method == "tools/call":
            tool_name = params.get("name")
            if not isinstance(tool_name, str) or tool_name not in self._tools:
                raise ToolInputError(f"Unknown tool: {tool_name}")
            tool_args = params.get("arguments", {})
            if not isinstance(tool_args, dict):
                raise ToolInputError("Tool arguments must be an object")

            raw_result = self._tools[tool_name].handler(tool_args)
            masked_text = mask_text(json.dumps(raw_result, indent=2, ensure_ascii=False))
            return {
                "content": [{"type": "text", "text": masked_text}],
                "structuredContent": raw_result,
            }
        return None

    def _build_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="list_jobs",
                title="List Jobs",
                description="List all freelance jobs in the workspace with optional filtering.",
                input_schema={
                    "type": "object",
                    "properties": {"include_finished": {"type": "boolean", "default": False}},
                },
                handler=self._tool_list_jobs,
            ),
            ToolDefinition(
                name="get_job_status",
                title="Get Job Status",
                description="Retrieve detailed status and metadata for a specific job ID.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_job_status,
            ),
            ToolDefinition(
                name="get_requirements",
                title="Get Requirements",
                description=(
                    "Fetch the requirements specification and acceptance criteria for a job."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_requirements,
            ),
            ToolDefinition(
                name="get_scope_changes",
                title="Get Scope Changes",
                description="List all analyzed scope change items and price proposals for a job.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_scope_changes,
            ),
            ToolDefinition(
                name="get_work_sessions",
                title="Get Work Sessions",
                description="Retrieve development work session history for a job.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_work_sessions,
            ),
            ToolDefinition(
                name="get_profitability",
                title="Get Profitability",
                description="Calculate margin, revenue, AI expense, and effective rate for a job.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_profitability,
            ),
            ToolDefinition(
                name="get_timeline",
                title="Get Business Timeline",
                description="Retrieve the append-only business event log for a job.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=self._tool_get_timeline,
            ),
            # Mutation tools
            ToolDefinition(
                name="create_job",
                title="Create Job",
                description="Create a new freelance job with client, description, and budget.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "client": {"type": "string"},
                        "description": {"type": "string"},
                        "source": {"type": "string", "default": "Other"},
                        "budget_pln": {"type": "number"},
                        "deadline": {"type": "string"},
                        "repository": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["client", "description"],
                },
                handler=self._tool_create_job,
            ),
            ToolDefinition(
                name="check_scope",
                title="Check Scope",
                description=(
                    "Analyze client request against current scope and calculate price surcharge."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "request_text": {"type": "string"},
                        "hourly_rate": {"type": "number", "default": 150.0},
                    },
                    "required": ["job_id", "request_text"],
                },
                handler=self._tool_check_scope,
            ),
        ]

    def _get_safe_job_dir(self, job_id_raw: object) -> tuple[str, Path]:
        if not isinstance(job_id_raw, str):
            raise ToolInputError("job_id must be a string")
        clean_id = job_id_raw.strip().upper()
        if not re.match(r"^JOB-\d+$", clean_id):
            raise ToolInputError(f"Invalid job ID format: '{job_id_raw}'")
        job_dir = self.manager.get_job_dir(clean_id)
        if not job_dir or not job_dir.exists():
            raise ToolInputError(f"Job {clean_id} not found")
        assert_safe_path(self.manager.config.workspace_path, job_dir)
        return clean_id, job_dir

    def _tool_list_jobs(self, args: JsonObject) -> JsonObject:
        include_finished = bool(args.get("include_finished", False))
        jobs = self.manager.list_jobs(include_finished=include_finished)
        return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}

    def _tool_get_job_status(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        job_file = job_dir / "job.json"
        if not job_file.exists():
            raise ToolInputError(f"Job {job_id} not found")
        try:
            job = load_job(job_file)
        except Exception as exc:
            raise ToolInputError(f"Job {job_id} could not be loaded: {exc}") from exc
        return {"job": job.to_dict(), "workspace_dir": job_dir.name}

    def _tool_get_requirements(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        req_path = job_dir / "analysis" / "requirements.json"
        if not req_path.exists():
            return {"job_id": job_id, "requirements": None, "status": "NOT_GENERATED"}
        data = safe_read_json(req_path)
        return {"job_id": job_id, "specification": data, "status": "AVAILABLE"}

    def _tool_get_scope_changes(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        detector = ScopeChangeDetector()
        changes = detector.list_changes(job_dir)
        return {"job_id": job_id, "changes": [c.to_dict() for c in changes], "count": len(changes)}

    def _tool_get_work_sessions(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        sessions = list_work_sessions(job_dir)
        return {
            "job_id": job_id,
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions),
        }

    def _tool_get_profitability(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        calc = ProfitabilityCalculator()
        report = calc.calculate(job_id, job_dir)
        return {"job_id": job_id, "profitability": report.to_dict()}

    def _tool_get_timeline(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        timeline = TimelineManager()
        events = timeline.list_events(job_dir)
        return {"job_id": job_id, "events": [e.to_dict() for e in events], "count": len(events)}

    def _tool_create_job(self, args: JsonObject) -> JsonObject:
        client = str(args.get("client", "")).strip()
        description = str(args.get("description", "")).strip()
        if not client or not description:
            raise ToolInputError("Client and description are required")
        source = str(args.get("source", "Other"))
        budget = (
            float(args["budget_pln"])
            if "budget_pln" in args and args["budget_pln"] is not None
            else None
        )
        deadline = str(args["deadline"]) if "deadline" in args and args["deadline"] else None
        repository = (
            str(args["repository"]) if "repository" in args and args["repository"] else None
        )
        notes = str(args.get("notes", ""))

        job = self.manager.create_job(
            client=client,
            description=description,
            source=source,
            budget_pln=budget,
            deadline=deadline,
            repository=repository,
            notes=notes,
        )
        return {"created": True, "job": job.to_dict()}

    def _tool_check_scope(self, args: JsonObject) -> JsonObject:
        job_id, job_dir = self._get_safe_job_dir(args.get("job_id"))
        text = str(args.get("request_text", "")).strip()
        if not text:
            raise ToolInputError("request_text is required")
        rate = float(args.get("hourly_rate", 150.0))

        req_path = job_dir / "analysis" / "requirements.json"
        spec = None
        if req_path.exists():
            spec = RequirementsSpec.from_dict(safe_read_json(req_path))

        detector = ScopeChangeDetector()
        with storage_lock(job_dir / "work" / ".scope.lock"):
            change_id = detector.next_change_id(job_dir)
            item = detector.analyze_request(
                job_id=job_id,
                change_id=change_id,
                requested_text=text,
                requirements_spec=spec,
                hourly_rate_pln=rate,
            )
            detector.save_change(item, job_dir)
        return {"analyzed": True, "scope_change": item.to_dict()}


def run_stdio_server(
    workspace_root: Path | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Run JSON-RPC 2.0 loop over STDIO."""
    in_stream = input_stream or sys.stdin
    out_stream = output_stream or sys.stdout

    server = FreelanceMcpServer(workspace_root=workspace_root)

    for line in in_stream:
        line_clean = line.strip()
        if not line_clean:
            continue
        try:
            msg = json.loads(line_clean)
        except json.JSONDecodeError:
            err = _rpc_error(None, -32700, "Parse error")
            out_stream.write(json.dumps(err) + "\n")
            out_stream.flush()
            continue

        response = server.handle(msg)
        if response is not None:
            out_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            out_stream.flush()


MCPServer = FreelanceMcpServer
