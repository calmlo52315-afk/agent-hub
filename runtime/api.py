from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from pathlib import Path

from runtime.orchestrator import Orchestrator, OrchestratorError


class RuntimeTaskRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1)
    mentioned_agent: str | None = None
    review_agent: str | None = None
    session_id: str | None = None


class RuntimeTaskRunResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool
    task_id: str | None = None
    trace_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None


class RuntimeTaskAcceptedResponse(BaseModel):
    task_id: str
    status: str
    poll_after_ms: int = 500


class RuntimeTaskStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    status: str
    completed: bool
    poll_after_ms: int = 500
    result: RuntimeTaskRunResponse | None = None
    error: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] | None = None


class RuntimeTaskCancelResponse(BaseModel):
    task_id: str
    status: str
    completed: bool


class RuntimeHealthResponse(BaseModel):
    status: str
    runtime_ready: bool


class WorkspaceSeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1024)
    content: str


class WorkspaceSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: list[WorkspaceSeedFile] = Field(min_length=0, max_length=5000)


class WorkspaceSeedResponse(BaseModel):
    seeded: int
    skipped: int
    errors: list[dict[str, str]] = Field(default_factory=list)


_orch_lock = threading.Lock()
_orch_instance: Orchestrator | None = None
_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub Runtime Internal API", version="1.0.0")

    @app.get("/healthz", response_model=RuntimeHealthResponse)
    def healthz() -> RuntimeHealthResponse:
        return RuntimeHealthResponse(status="ok", runtime_ready=True)

    # ── Agent CRUD ──────────────────────────────────────────────
    # ⭐ 用户自定义 Agent API — 数据 agent（非 runtime），存在 user_agents.json

    class AgentDefinitionRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        id: str | None = None  # 不传则从 name 自动生成
        name: str = Field(min_length=1, max_length=64)
        avatar: str = ""
        description: str = ""
        system_prompt: str = ""
        allowed_skills: list[str] = Field(default_factory=list)
        preferred_provider: str = "claude_code"
        visibility: str = "private"
        import_url: str = ""  # ⭐ 从第三方 URL 导入 skills/tools

    class AgentDefinitionResponse(BaseModel):
        model_config = ConfigDict(extra="allow")
        id: str
        name: str
        avatar: str
        description: str
        system_prompt: str
        allowed_skills: list[str]
        preferred_provider: str
        visibility: str
        created_by: str
        created_at: str
        updated_at: str
        import_url: str = ""

    class AgentListResponse(BaseModel):
        agents: list[AgentDefinitionResponse]

    def _agent_loader() -> "PersonaLoader":
        from runtime.agents.persona import PersonaLoader
        return PersonaLoader()

    def _agent_to_response(agent: "AgentDefinition") -> AgentDefinitionResponse:
        return AgentDefinitionResponse(
            id=agent.id,
            name=agent.name,
            avatar=agent.avatar,
            description=agent.description,
            system_prompt=agent.system_prompt,
            allowed_skills=list(agent.allowed_skills),
            preferred_provider=agent.preferred_provider,
            visibility=agent.visibility,
            created_by=getattr(agent, "created_by", "user"),
            created_at=getattr(agent, "created_at", ""),
            updated_at=getattr(agent, "updated_at", ""),
            import_url=getattr(agent, "import_url", ""),
        )

    @app.get("/api/v1/agents", response_model=AgentListResponse)
    def list_agents() -> AgentListResponse:
        loader = _agent_loader()
        all_agents = loader.list_all()
        return AgentListResponse(agents=[_agent_to_response(a) for a in all_agents])

    @app.post("/api/v1/agents", status_code=status.HTTP_201_CREATED)
    def create_agent(
        request: AgentDefinitionRequest,
        _: None = Depends(require_internal_token),
    ) -> AgentDefinitionResponse:
        loader = _agent_loader()

        # ⭐ 如果提供了 import_url，从该 URL 拉取 skills/tools 配置
        extra_skills: list[str] = []
        if request.import_url:
            try:
                import requests as _requests
                resp = _requests.get(request.import_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    extra_skills = data.get("skills") or data.get("tools") or []
                elif isinstance(data, list):
                    extra_skills = data
                if isinstance(extra_skills, list):
                    extra_skills = [str(s) for s in extra_skills[:20]]  # 限制 20 个
            except Exception as e:
                logger.warning(f"[Agent API] Failed to import from {request.import_url}: {e}")

        raw = request.model_dump()
        raw["allowed_skills"] = (request.allowed_skills or []) + extra_skills
        if "import_url" not in raw:
            raw["import_url"] = request.import_url

        agent = loader.add_user_agent(raw)
        return _agent_to_response(agent)

    @app.delete("/api/v1/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_agent(
        agent_id: str,
        _: None = Depends(require_internal_token),
    ) -> None:
        loader = _agent_loader()
        if not loader.delete_user_agent(agent_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found or is not a user agent",
            )
        return None

    # ── Task API ────────────────────────────────────────────────

    @app.post("/internal/v1/tasks", response_model=RuntimeTaskAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
    def submit_task(
        request: RuntimeTaskRunRequest,
        _: None = Depends(require_internal_token),
    ) -> RuntimeTaskAcceptedResponse:
        task_id = f"runtime_job_{uuid.uuid4().hex[:16]}"
        shared_diag: list[dict[str, Any]] = []
        with _jobs_lock:
            _jobs[task_id] = {
                "status": "queued",
                "completed": False,
                "submitted_at": time.time(),
                "cancel_requested": False,
                "result": None,
                "error": None,
                "diagnostics": shared_diag,
            }
        worker = threading.Thread(
            target=_execute_job,
            args=(task_id, request.instruction, shared_diag, request.mentioned_agent, request.review_agent, request.session_id),
            daemon=True,
        )
        worker.start()
        return RuntimeTaskAcceptedResponse(task_id=task_id, status="queued")

    @app.get("/internal/v1/tasks/{task_id}", response_model=RuntimeTaskStatusResponse)
    def get_task_status(
        task_id: str,
        _: None = Depends(require_internal_token),
    ) -> RuntimeTaskStatusResponse:
        with _jobs_lock:
            job = _jobs.get(task_id)
            if job is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "runtime_task_not_found",
                        "message": "runtime task not found",
                    },
                )
            result = job.get("result")
            diag = job.get("diagnostics")
            diag_snapshot = list(diag) if diag is not None else None
            return RuntimeTaskStatusResponse(
                task_id=task_id,
                status=job["status"],
                completed=job["completed"],
                poll_after_ms=500,
                result=RuntimeTaskRunResponse.model_validate(result) if result else None,
                error=job.get("error"),
                diagnostics=diag_snapshot,
            )

    @app.delete("/internal/v1/tasks/{task_id}", response_model=RuntimeTaskCancelResponse)
    def cancel_task(
        task_id: str,
        _: None = Depends(require_internal_token),
    ) -> RuntimeTaskCancelResponse:
        with _jobs_lock:
            job = _jobs.get(task_id)
            if job is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "runtime_task_not_found",
                        "message": "runtime task not found",
                    },
                )
            if job["completed"]:
                return RuntimeTaskCancelResponse(task_id=task_id, status=job["status"], completed=True)
            job["cancel_requested"] = True
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["completed"] = True
                job["error"] = {
                    "code": "runtime_task_cancelled",
                    "message": "runtime task was cancelled before execution",
                }
            elif job["status"] == "running":
                job["status"] = "cancelling"
            return RuntimeTaskCancelResponse(task_id=task_id, status=job["status"], completed=job["completed"])

    @app.get("/internal/v1/sessions/{session_id}/workspace/files")
    def get_workspace_files(
        session_id: str,
        _: None = Depends(require_internal_token),
    ) -> list[dict[str, Any]]:
        """Return the workspace file tree.

        ⭐ Stage 9: 对 imported 工作区，直接从 source_path（用户原始目录）读取文件。
        对 scratch/project，从 workspace/{session_id}/source/ 读取。
        """
        import hashlib
        import json as _json

        repo_root = Path(__file__).resolve().parents[1]

        # 读取 workspace meta 确定 source_root
        meta_path = repo_root / "workspace" / session_id / "workspace_meta.json"
        workspace_type = "scratch"
        source_path_for_type = None
        if meta_path.exists():
            try:
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
                workspace_type = meta.get("workspace_type", "scratch")
                source_path_for_type = meta.get("source_path")
            except Exception:
                pass

        # imported: 直接读用户的原始目录；否则读 source/
        if workspace_type == "imported" and source_path_for_type:
            source_root = Path(source_path_for_type).resolve()
        else:
            source_root = repo_root / "workspace" / session_id / "source"

        def walk_dir(root: Path, rel_path: str = "") -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            if not root.exists():
                return items
            try:
                entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                return items
            for entry in entries:
                entry_rel = f"{rel_path}/{entry.name}" if rel_path else entry.name
                if entry.is_dir():
                    if entry.name.startswith("."):
                        continue
                    # ⭐ 过滤无关的系统目录 — 用户只关心自己的代码
                    if entry.name in ("workspace", "gateway", "artifacts", "__pycache__", "node_modules", ".git"):
                        continue
                    children = walk_dir(entry, entry_rel)
                    if not children:
                        continue  # 跳过空目录
                    items.append({
                        "name": entry.name,
                        "path": entry_rel,
                        "type": "directory",
                        "children": children,
                    })
                elif entry.is_file():
                    try:
                        st = entry.stat()
                        size = st.st_size
                        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
                    except OSError:
                        size = 0
                        mtime = ""
                    sha256_hash = ""
                    try:
                        h = hashlib.sha256()
                        with open(entry, "rb") as fh:
                            chunk = fh.read(65536)
                            h.update(chunk)
                        sha256_hash = h.hexdigest()
                    except Exception:
                        sha256_hash = ""
                    items.append({
                        "name": entry.name,
                        "path": entry_rel,
                        "type": "file",
                        "size_bytes": size,
                        "sha256_hash": sha256_hash,
                        "updated_at": mtime,
                    })
            return items

        return walk_dir(source_root)

    @app.post("/internal/v1/sessions/{session_id}/workspace/seed", response_model=WorkspaceSeedResponse)
    def seed_workspace(
        session_id: str,
        request: WorkspaceSeedRequest,
        _: None = Depends(require_internal_token),
    ) -> WorkspaceSeedResponse:
        """Seed an imported workspace — 记录文件索引。

        ⭐ Stage 9: imported 工作区直接操作原始目录。seed 写入 workspace_meta
        记录 source_path，供后续文件树查询定位用户原始目录。
        文件本身不需要复制——Agent 直接在用户原始目录读写。
        """
        import json as _json
        from datetime import datetime as dt, timezone as tz

        repo_root = Path(__file__).resolve().parents[1]
        session_root = repo_root / "workspace" / session_id
        session_root.mkdir(parents=True, exist_ok=True)

        source_dir = session_root / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "workspace_id": session_id,
            "session_id": session_id,
            "root_path": str(session_root),
            "workspace_type": "imported",
            "source_path": str(source_dir),
            "created_at": dt.now(tz.utc).isoformat(),
            "updated_at": dt.now(tz.utc).isoformat(),
            "status": "active",
        }
        meta_path = session_root / "workspace_meta.json"
        meta_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2))

        return WorkspaceSeedResponse(seeded=len(request.files), skipped=0, errors=[])

    class WorkspaceFilesContentRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        paths: list[str] = Field(min_length=0, max_length=500)

    def _read_files_content(session_id: str, paths: list[str]) -> dict[str, Any]:
        """内部：从磁盘读取文件内容。

        ⭐ Stage 9: 对 imported 工作区，从 source_path 读取。
        """
        import json as _json

        repo_root = Path(__file__).resolve().parents[1]

        # 读取 workspace meta 确定 source_root
        meta_path = repo_root / "workspace" / session_id / "workspace_meta.json"
        if meta_path.exists():
            try:
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
                ws_type = meta.get("workspace_type", "scratch")
                src_path = meta.get("source_path")
                if ws_type == "imported" and src_path:
                    source_root = Path(src_path).resolve()
                else:
                    source_root = (repo_root / "workspace" / session_id / "source").resolve()
            except Exception:
                source_root = (repo_root / "workspace" / session_id / "source").resolve()
        else:
            source_root = (repo_root / "workspace" / session_id / "source").resolve()

        contents: dict[str, str | None] = {}
        errors: list[dict[str, str]] = []

        for file_path in paths:
            abs_path = (source_root / file_path).resolve()
            try:
                abs_path.relative_to(source_root)
            except ValueError:
                errors.append({"path": file_path, "error": "path_traversal"})
                contents[file_path] = None
                continue
            try:
                contents[file_path] = abs_path.read_text(encoding="utf-8")
            except Exception as exc:
                errors.append({"path": file_path, "error": str(exc)})
                contents[file_path] = None

        return {"contents": contents, "errors": errors}

    @app.post("/internal/v1/sessions/{session_id}/workspace/files-content")
    def read_workspace_files_content(
        session_id: str,
        request: WorkspaceFilesContentRequest,
        _: None = Depends(require_internal_token),
    ) -> dict[str, Any]:
        """批量读取文件内容（保留用于同步/批量场景）。"""
        return _read_files_content(session_id, request.paths)

    @app.get("/internal/v1/sessions/{session_id}/workspace/file")
    def read_workspace_file(
        session_id: str,
        path: str = Query(min_length=1, max_length=1024),
        _: None = Depends(require_internal_token),
    ) -> dict[str, Any]:
        """按需读取单个文件内容（VSCode 懒加载模式）。"""
        result = _read_files_content(session_id, [path])
        content = result["contents"].get(path)
        return {"path": path, "content": content}

    return app


def get_orchestrator(session_id: str | None = None) -> Orchestrator:
    global _orch_instance
    if session_id is None:
        session_id = "default"
    if _orch_instance is not None and getattr(_orch_instance, "session_id", None) != session_id:
        _orch_instance = None
    if _orch_instance is not None:
        return _orch_instance
    with _orch_lock:
        if _orch_instance is None:
            _orch_instance = Orchestrator.load(session_id=session_id)
    return _orch_instance


def require_internal_token(x_runtime_token: str = Header(default="")) -> None:
    expected = os.getenv("RUNTIME_INTERNAL_TOKEN", "runtime-internal-token")
    if x_runtime_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "runtime_unauthorized",
                "message": "invalid runtime internal token",
            },
        )


def _execute_job(task_id: str, instruction: str, shared_diag: list[dict[str, Any]] | None = None, mentioned_agent: str | None = None, review_agent: str | None = None, session_id: str | None = None) -> None:
    with _jobs_lock:
        if task_id not in _jobs:
            return
        if _jobs[task_id]["completed"]:
            return
        _jobs[task_id]["status"] = "running"

    # ⭐ Stage 10: 启动日志直接写 stderr 确保可见
    import sys as _sys
    _sys.stderr.write(f"[RUNTIME] _execute_job START: task={task_id[:16]}..., session={session_id}, agent={mentioned_agent}, review={review_agent}\n")
    _sys.stderr.flush()

    try:
        orch = get_orchestrator(session_id=session_id)
    except Exception as exc:
        _sys.stderr.write(f"[RUNTIME] Orchestrator load FAILED: {exc}\n")
        _sys.stderr.flush()
        import traceback as _tb
        _tb.print_exc(file=_sys.stderr)
        with _jobs_lock:
            if task_id in _jobs:
                _jobs[task_id]["status"] = "failed"
                _jobs[task_id]["completed"] = True
                _jobs[task_id]["error"] = {
                    "code": "runtime_load_error",
                    "message": str(exc),
                }
        return
    try:
        raw = orch.run_task(instruction=instruction, mentioned_agent=mentioned_agent, review_agent=review_agent, _shared_diag=shared_diag)

        # 适配 Gateway 的 RunResult 格式
        pipeline_result = raw.get("result") or {}
        coding_wrapped = pipeline_result.get("coding") or {}
        coding_flat = dict(coding_wrapped)
        agent_output = coding_wrapped.get("agent_output") or {}
        if isinstance(agent_output, dict):
            for key in ("changes", "example_diff"):
                if key in agent_output and key not in coding_flat:
                    coding_flat[key] = agent_output[key]

        adapted = {
            "ok": raw.get("ok", False),
            "task_id": raw.get("task_id"),
            "trace_id": raw.get("trace_id"),
            "messages": raw.get("messages") or [],
            "diagnostics": raw.get("diagnostics") or [],
            "result": {
                "execution_model": pipeline_result.get("execution_model"),
                "coding": coding_flat,
                "coding_subtasks": [coding_flat],
                # ⭐ 保留 review 原始值（dict 或 sentinel），不要用 or {} 吞掉有意义的 dict
                "review": pipeline_result.get("review") if pipeline_result.get("review") is not None else {},
                "artifact": pipeline_result.get("artifact") or {},
                "task_plan": pipeline_result.get("task_plan") or {},
                "used_skills": pipeline_result.get("used_skills") or [],
            },
        }
        if not raw.get("ok"):
            adapted["failure"] = raw.get("failure") or {}

        with _jobs_lock:
            if task_id not in _jobs:
                return
            if _jobs[task_id]["cancel_requested"]:
                _jobs[task_id]["status"] = "cancelled"
                _jobs[task_id]["completed"] = True
                _jobs[task_id]["result"] = None
                _jobs[task_id]["error"] = {
                    "code": "runtime_task_cancelled",
                    "message": "runtime task was cancelled",
                }
                return
            _jobs[task_id]["status"] = "completed"
            _jobs[task_id]["completed"] = True
            _jobs[task_id]["result"] = adapted
    except OrchestratorError as exc:
        with _jobs_lock:
            if task_id not in _jobs:
                return
            if _jobs[task_id]["cancel_requested"]:
                _jobs[task_id]["status"] = "cancelled"
                _jobs[task_id]["completed"] = True
                _jobs[task_id]["result"] = None
                _jobs[task_id]["error"] = {
                    "code": "runtime_task_cancelled",
                    "message": "runtime task was cancelled",
                }
                return
            _jobs[task_id]["status"] = "failed"
            _jobs[task_id]["completed"] = True
            _jobs[task_id]["error"] = {
                "code": "runtime_orchestrator_error",
                "message": str(exc),
            }


app = create_app()
