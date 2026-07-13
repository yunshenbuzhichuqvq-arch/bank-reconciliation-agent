from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent

COMPOSE_PATH = REPO_ROOT / "compose.yaml"
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"
FRONTEND_DOCKERFILE_PATH = REPO_ROOT / "frontend" / "Dockerfile"
FRONTEND_DOCKERIGNORE_PATH = REPO_ROOT / "frontend" / ".dockerignore"
FRONTEND_PACKAGE_JSON_PATH = REPO_ROOT / "frontend" / "package.json"
FRONTEND_VITE_CONFIG_PATH = REPO_ROOT / "frontend" / "vite.config.ts"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

REQUIRED_SERVICES = {"backend", "worker", "frontend", "mysql", "redis"}
REQUIRED_VOLUMES = {"mysql_data", "redis_data", "uploads_data"}


# ---------------------------------------------------------------------------
# compose.yaml tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compose_data() -> dict:
    if not COMPOSE_PATH.exists():
        pytest.fail(f"compose.yaml not found at {COMPOSE_PATH}")
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_compose_services_exact_set(compose_data: dict) -> None:
    services = set(compose_data.get("services", {}).keys())
    assert services == REQUIRED_SERVICES, f"Expected {REQUIRED_SERVICES}, got {services}"


def test_compose_volumes(compose_data: dict) -> None:
    volumes = set(compose_data.get("volumes", {}).keys())
    assert volumes == REQUIRED_VOLUMES, f"Expected {REQUIRED_VOLUMES}, got {volumes}"


def test_backend_worker_share_image_and_uploads(compose_data: dict) -> None:
    services = compose_data["services"]
    backend = services["backend"]
    worker = services["worker"]

    assert "build" in backend, "backend must have build key"
    assert "build" in worker, "worker must have build key"
    assert backend["build"] == worker["build"], "backend and worker must share same build definition"
    assert "image" not in backend, "backend should not have image key when using build"
    assert "image" not in worker, "worker should not have image key when using build"

    backend_command = backend.get("command", "")
    worker_command = worker.get("command", "")
    assert backend_command != worker_command, (
        f"backend and worker must have different commands: {backend_command!r} vs {worker_command!r}"
    )
    assert "uvicorn" in str(backend_command), "backend command must include uvicorn"
    assert "arq" in str(worker_command), "worker command must include arq"

    backend_vols = [v.split(":")[0] if isinstance(v, str) else v for v in backend.get("volumes", [])]
    worker_vols = [v.split(":")[0] if isinstance(v, str) else v for v in worker.get("volumes", [])]

    assert any("uploads_data" in str(v) for v in backend_vols), (
        "backend must mount uploads_data"
    )
    assert any("uploads_data" in str(v) for v in worker_vols), (
        "worker must mount uploads_data"
    )


def test_backend_worker_env_mysql_redis_fake_async(compose_data: dict) -> None:
    for service_name in ("backend", "worker"):
        env = _collect_service_env(compose_data, service_name)
        mysql_dsn = env.get("MYSQL_DSN", "")
        redis_dsn = env.get("REDIS_DSN", "")
        assert "@mysql:" in mysql_dsn or "mysql:" in mysql_dsn, (
            f"{service_name} MYSQL_DSN must use 'mysql' host: {mysql_dsn!r}"
        )
        assert "127.0.0.1" not in mysql_dsn, (
            f"{service_name} MYSQL_DSN must not use 127.0.0.1"
        )
        assert "@redis:" in redis_dsn or "redis:" in redis_dsn, (
            f"{service_name} REDIS_DSN must use 'redis' host: {redis_dsn!r}"
        )
        assert "127.0.0.1" not in redis_dsn, (
            f"{service_name} REDIS_DSN must not use 127.0.0.1"
        )
        assert env.get("LLM_PROVIDER") == "fake", (
            f"{service_name} LLM_PROVIDER default must be fake"
        )
        assert env.get("EMBEDDING_BACKEND") == "hash", (
            f"{service_name} EMBEDDING_BACKEND default must be hash"
        )
        assert env.get("ASYNC_QUEUE_ENABLED") == "true", (
            f"{service_name} ASYNC_QUEUE_ENABLED default must be true"
        )


def test_mysql_redis_not_expose_host_ports(compose_data: dict) -> None:
    mysql_ports = compose_data["services"]["mysql"].get("ports", [])
    redis_ports = compose_data["services"]["redis"].get("ports", [])
    assert not mysql_ports, f"mysql must not expose host ports: {mysql_ports}"
    assert not redis_ports, f"redis must not expose host ports: {redis_ports}"


def test_host_exposed_ports_only_backend_frontend(compose_data: dict) -> None:
    host_ports = {
        name: svc.get("ports", [])
        for name, svc in compose_data["services"].items()
        if svc.get("ports")
    }
    assert set(host_ports.keys()) <= {"backend", "frontend"}, (
        f"Only backend/frontend may expose host ports: {host_ports}"
    )
    assert any("8000" in p for p in host_ports.get("backend", [])), (
        "backend must expose port 8000"
    )
    assert any("4173" in p for p in host_ports.get("frontend", [])), (
        "frontend must expose port 4173"
    )


def test_all_services_have_health_or_depends(compose_data: dict) -> None:
    services = compose_data["services"]
    for name, svc in services.items():
        has_health = "healthcheck" in svc
        depends = svc.get("depends_on", {})
        has_healthy_dep = any(
            isinstance(v, dict) and v.get("condition") == "service_healthy"
            for v in depends.values()
        )
        assert has_health or has_healthy_dep, (
            f"Service '{name}' must have healthcheck or depend on service_healthy"
        )


def test_mysql_healthcheck_uses_root_password(compose_data: dict) -> None:
    hc = compose_data["services"]["mysql"]["healthcheck"]
    test_cmd = yaml.dump(hc.get("test", ""))
    assert "MYSQL_ROOT_PASSWORD" in test_cmd or "password" in test_cmd.lower(), (
        "mysql healthcheck must reference root password"
    )
    assert "mysqladmin" in str(hc.get("test", "")) or "mysqladmin" in test_cmd, (
        "mysql healthcheck must use mysqladmin"
    )


def test_frontend_depends_backend_healthy(compose_data: dict) -> None:
    depends = compose_data["services"]["frontend"].get("depends_on", {})
    backend_dep = depends.get("backend")
    assert isinstance(backend_dep, dict) and backend_dep.get("condition") == "service_healthy", (
        "frontend must depend on backend with condition: service_healthy"
    )


# ---------------------------------------------------------------------------
# Dockerfile tests
# ---------------------------------------------------------------------------

def test_dockerfile_exists() -> None:
    assert DOCKERFILE_PATH.exists(), f"Dockerfile not found at {DOCKERFILE_PATH}"


def test_dockerfile_no_env_no_secret() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert ".env" not in content, "Dockerfile must not copy .env"
    assert "ENV DEEPSEEK_API_KEY" not in content, "Dockerfile must not set DEEPSEEK_API_KEY in ENV"
    assert "ENV JWT_SECRET_KEY" not in content, "Dockerfile must not set JWT_SECRET_KEY in ENV"


def test_dockerfile_uses_python_slim_bookworm() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "python:3.11-slim-bookworm" in content or "FROM python:3.11-slim" in content, (
        "Dockerfile must base on python:3.11-slim-bookworm"
    )


def test_dockerfile_uses_uv_frozen() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "uv==" in content, "Dockerfile must pin uv version"
    assert "--frozen" in content, "Dockerfile must use uv sync --frozen"


def test_dockerfile_copies_package_metadata_before_sync() -> None:
    lines = DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines()
    sync_line = None
    readme_line = None
    src_line = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("RUN uv sync"):
            sync_line = i
        if stripped.startswith("COPY ") and "README.md" in stripped:
            readme_line = i
        if stripped == "COPY src/ ./src/":
            if src_line is None:
                src_line = i
    assert readme_line is not None, "Dockerfile must COPY README.md"
    assert src_line is not None, "Dockerfile must COPY src/ before uv sync"
    assert readme_line < sync_line, (
        f"README.md COPY (line {readme_line + 1}) must be before uv sync (line {sync_line + 1})"
    )
    assert src_line < sync_line, (
        f"src/ COPY (line {src_line + 1}) must be before uv sync (line {sync_line + 1})"
    )


def test_dockerfile_no_embedding_install() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "[embedding]" not in content, "Dockerfile must not install embedding extra"


def test_dockerfile_sets_pythonpath_workdir() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "/app" in content, "Dockerfile must set WORKDIR /app"
    assert "PYTHONPATH" in content, "Dockerfile must set PYTHONPATH"


def test_dockerignore_exists() -> None:
    assert DOCKERIGNORE_PATH.exists(), f".dockerignore not found at {DOCKERIGNORE_PATH}"


def test_dockerfile_copies_prompts() -> None:
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "COPY prompts/ ./prompts/" in content, (
        "Dockerfile must COPY prompts/ ./prompts/"
    )


def test_dockerignore_has_prompts_md() -> None:
    content = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
    assert "!prompts/*.md" in content, (
        ".dockerignore must re-include prompts/*.md"
    )


def test_dockerignore_excludes_env_and_runtime() -> None:
    content = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
    assert ".env" in content, ".dockerignore must exclude .env"
    assert "__pycache__" in content or "**.pyc" in content, ".dockerignore must exclude Python cache"


# ---------------------------------------------------------------------------
# Frontend Dockerfile tests
# ---------------------------------------------------------------------------

def test_frontend_dockerfile_exists() -> None:
    assert FRONTEND_DOCKERFILE_PATH.exists(), (
        f"frontend/Dockerfile not found at {FRONTEND_DOCKERFILE_PATH}"
    )


def test_frontend_dockerfile_no_nginx() -> None:
    content = FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "nginx" not in content.lower(), "frontend Dockerfile must not use Nginx"


def test_frontend_dockerfile_uses_vite_preview() -> None:
    content = FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "preview" in content, "frontend Dockerfile must use vite preview"


def test_frontend_dockerfile_uses_node_22() -> None:
    content = FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "node:22" in content, "frontend Dockerfile must base on node:22"


def test_frontend_dockerignore_exists() -> None:
    assert FRONTEND_DOCKERIGNORE_PATH.exists(), (
        f"frontend/.dockerignore not found at {FRONTEND_DOCKERIGNORE_PATH}"
    )


# ---------------------------------------------------------------------------
# Frontend package.json tests
# ---------------------------------------------------------------------------

def test_frontend_package_json_has_preview_script() -> None:
    data = json.loads(FRONTEND_PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    assert "preview" in data.get("scripts", {}), (
        "frontend/package.json must have 'preview' script"
    )


# ---------------------------------------------------------------------------
# Frontend vite.config.ts tests
# ---------------------------------------------------------------------------

def test_vite_config_proxy_target() -> None:
    content = FRONTEND_VITE_CONFIG_PATH.read_text(encoding="utf-8")
    assert "VITE_API_PROXY_TARGET" in content, (
        "vite.config.ts must reference VITE_API_PROXY_TARGET"
    )
    assert "server" in content and "proxy" in content, (
        "vite.config.ts must configure server.proxy"
    )
    assert "preview" in content and "proxy" in content, (
        "vite.config.ts must configure preview.proxy"
    )


# ---------------------------------------------------------------------------
# .env.example tests
# ---------------------------------------------------------------------------

REQUIRED_ENV_KEYS = {
    "APP_NAME", "APP_ENV", "API_V1_PREFIX",
    "JWT_SECRET_KEY", "JWT_ALGORITHM", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "DEMO_USER_PASSWORD",
    "MYSQL_DSN", "CHROMA_PATH", "UPLOAD_DIR",
    "CHECKPOINT_ENABLED", "CHECKPOINT_SQLITE_PATH",
    "REDIS_DSN", "ASYNC_QUEUE_ENABLED", "JOB_IDEMPOTENCY_TTL_SECONDS",
    "ARQ_JOB_MAX_ATTEMPTS", "ARQ_JOB_TIMEOUT_SECONDS",
    "LLM_PROVIDER", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL",
    "LLM_TIMEOUT_SECONDS", "LLM_MAX_ATTEMPTS",
    "LLM_BACKOFF_BASE_SECONDS", "LLM_BACKOFF_MAX_SECONDS",
    "LLM_BREAKER_FAIL_THRESHOLD", "LLM_BREAKER_OPEN_SECONDS",
    "ENABLE_LLM_CACHE", "LLM_CACHE_TTL_SECONDS",
    "ENABLE_LLM_RATE_LIMIT", "LLM_RATE_LIMIT_RPM", "LLM_RATE_LIMIT_MAX_CONCURRENCY",
    "LLM_RATE_LIMIT_MAX_WAIT_SECONDS", "LLM_RATE_LIMIT_WINDOW_SECONDS",
    "EMBEDDING_BACKEND",
    "ENABLE_RAG_REWRITE", "ENABLE_RAG_HYBRID", "ENABLE_RAG_RERANKER",
    "RAG_DENSE_TOP_N", "RAG_BM25_TOP_N", "RAG_RERANK_TOP_K", "RAG_RRF_K",
    "RAG_DENSE_MIN_SCORE", "RAG_DENSE_MIN_SCORE_BGE_SMALL",
    "RAG_DENSE_MIN_SCORE_BGE_M3", "RAG_RERANKER_MIN_SCORE",
    "RAG_LOW_SCORE", "RAG_BREAKER_FAIL_THRESHOLD", "RAG_BREAKER_OPEN_SECONDS",
    "CUTOFF_WINDOW",
    "DECISION_REGRESSION_RUNS", "MAX_UPLOAD_BYTES", "MAX_UPLOAD_ROWS",
}


def _parse_env_keys(filepath: Path) -> set[str]:
    keys: set[str] = set()
    pattern = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=")
    for line in filepath.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            keys.add(match.group(1))
    return keys


def test_env_example_covers_all_settings_keys() -> None:
    env_keys = _parse_env_keys(ENV_EXAMPLE_PATH)
    missing = REQUIRED_ENV_KEYS - env_keys
    assert not missing, f".env.example missing keys: {missing}"


def test_env_example_no_longer_declares_trace_dir() -> None:
    # Stage 29 retired local JSON Trace; TRACE_DIR must not reappear.
    env_keys = _parse_env_keys(ENV_EXAMPLE_PATH)
    assert "TRACE_DIR" not in env_keys


def test_env_example_no_real_secret() -> None:
    content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    deepseek_match = re.search(r'DEEPSEEK_API_KEY\s*=\s*"([^"]*)"', content)
    if deepseek_match:
        assert deepseek_match.group(1) == "", (
            "DEEPSEEK_API_KEY must be empty string"
        )



# ---------------------------------------------------------------------------
# CI workflow tests
# ---------------------------------------------------------------------------

CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_JOB_IDS = {
    "backend-quality",
    "frontend-quality",
    "deterministic-eval",
    "delivery-smoke",
}


@pytest.fixture(scope="module")
def ci_workflow_data() -> dict:
    if not CI_WORKFLOW_PATH.exists():
        pytest.fail(f".github/workflows/ci.yml not found at {CI_WORKFLOW_PATH}")
    return yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_ci_triggers(ci_workflow_data: dict) -> None:
    triggers = ci_workflow_data.get("on", ci_workflow_data.get(True, {}))
    trigger_types = set(triggers.keys()) if isinstance(triggers, dict) else set()
    assert "pull_request" in trigger_types or True in trigger_types, (
        "CI must trigger on pull_request"
    )
    assert "workflow_dispatch" in trigger_types, "CI must support workflow_dispatch"


def test_ci_permissions_readonly(ci_workflow_data: dict) -> None:
    permissions = ci_workflow_data.get("permissions", {})
    assert permissions.get("contents") == "read", "CI must have contents: read only"
    for perm_key in ("issues", "deployments", "packages", "pull-requests"):
        val = permissions.get(perm_key, "read")
        assert val != "write", f"CI must not have write permission for {perm_key}"


def test_ci_job_ids(ci_workflow_data: dict) -> None:
    jobs = set(ci_workflow_data.get("jobs", {}).keys())
    assert jobs == REQUIRED_JOB_IDS, f"Expected {REQUIRED_JOB_IDS}, got {jobs}"


def test_delivery_smoke_needs_all_others(ci_workflow_data: dict) -> None:
    delivery = ci_workflow_data["jobs"]["delivery-smoke"]
    needs = delivery.get("needs", [])
    expected = sorted(["backend-quality", "frontend-quality", "deterministic-eval"])
    assert sorted(needs) == expected, f"delivery-smoke must need {expected}, got {needs}"


def test_ci_runner_versions(ci_workflow_data: dict) -> None:
    for job_id in ("backend-quality", "delivery-smoke"):
        runner = ci_workflow_data["jobs"][job_id].get("runs-on", "")
        assert "ubuntu-24.04" in runner, f"{job_id} must run on ubuntu-24.04"


def test_ci_python_version(ci_workflow_data: dict) -> None:
    python_jobs = ("backend-quality", "deterministic-eval", "delivery-smoke")
    for job_id in python_jobs:
        steps_text = yaml.dump(ci_workflow_data["jobs"][job_id].get("steps", []))
        assert "setup-python@v5" in steps_text, f"{job_id} must use setup-python@v5"
        assert 'python-version: "3.11"' in steps_text or "python-version: '3.11'" in steps_text, (
            f"{job_id} must pin python-version: 3.11"
        )


def test_backend_quality_uses_frozen_uv(ci_workflow_data: dict) -> None:
    backend = ci_workflow_data["jobs"]["backend-quality"]
    steps_text = yaml.dump(backend.get("steps", []))
    assert "--frozen" in steps_text, "backend-quality must use uv sync --frozen"
    assert "uv run pytest" in steps_text, "backend-quality must run pytest"
    assert "uv run ruff" in steps_text, "backend-quality must run ruff"


def test_frontend_quality_uses_npm_ci(ci_workflow_data: dict) -> None:
    frontend = ci_workflow_data["jobs"]["frontend-quality"]
    steps_text = yaml.dump(frontend.get("steps", []))
    assert "npm ci" in steps_text, "frontend-quality must use npm ci"
    assert "npm run test" in steps_text, "frontend-quality must run test"
    assert "npm run typecheck" in steps_text, "frontend-quality must run typecheck"
    assert "npm run build" in steps_text, "frontend-quality must run build"


def test_backend_quality_uses_fake_hash(ci_workflow_data: dict) -> None:
    backend = ci_workflow_data["jobs"]["backend-quality"]
    env = backend.get("env", {})
    assert env.get("LLM_PROVIDER") == "fake", (
        "backend-quality must have LLM_PROVIDER=fake"
    )
    assert env.get("EMBEDDING_BACKEND") == "hash", (
        "backend-quality must have EMBEDDING_BACKEND=hash"
    )
    steps_text = yaml.dump(backend.get("steps", []))
    assert "uv run pytest" in steps_text, "backend-quality must run pytest"
    assert "uv run ruff" in steps_text, "backend-quality must run ruff"


def test_deterministic_eval_uses_fake_hash(ci_workflow_data: dict) -> None:
    job = ci_workflow_data["jobs"]["deterministic-eval"]
    steps_text = yaml.dump(job.get("steps", []))
    env_text = yaml.dump(job.get("env", {}))
    assert "LLM_PROVIDER" in env_text and "fake" in env_text, (
        "eval must use LLM_PROVIDER=fake"
    )
    assert "EMBEDDING_BACKEND" in env_text and "hash" in env_text, (
        "eval must use EMBEDDING_BACKEND=hash"
    )
    assert "--fail-on-release-block" not in steps_text, (
        "eval must not use --fail-on-release-block"
    )


def test_deterministic_eval_fresh_harness(ci_workflow_data: dict) -> None:
    steps_text = yaml.dump(ci_workflow_data["jobs"]["deterministic-eval"].get("steps", []))
    assert "eval_harness" in steps_text, "eval must run harness"
    assert "eval_gates" in steps_text, "eval must run gates"
    assert "baseline" in steps_text, "eval must generate fresh baseline"


def test_delivery_smoke_twice(ci_workflow_data: dict) -> None:
    steps_text = yaml.dump(ci_workflow_data["jobs"]["delivery-smoke"].get("steps", []))
    assert "smoke-run-1" in steps_text, "delivery must produce smoke-run-1"
    assert "smoke-run-2" in steps_text, "delivery must produce smoke-run-2"
    assert "docker compose up" in steps_text, "delivery must start compose"
    assert "docker compose down" in steps_text, "delivery must clean up compose"


def test_delivery_smoke_always_cleanup(ci_workflow_data: dict) -> None:
    delivery = ci_workflow_data["jobs"]["delivery-smoke"]
    steps_text = yaml.dump(delivery.get("steps", []))
    assert "always()" in steps_text, "delivery cleanup must use always()"


def test_ci_no_deepseek_key(ci_workflow_data: dict) -> None:
    text = yaml.dump(ci_workflow_data)
    assert "DEEPSEEK_API_KEY" not in text, "CI must not reference DEEPSEEK_API_KEY"
    assert "git push" not in text, "CI must not git push"


def test_ci_no_secrets_ref(ci_workflow_data: dict) -> None:
    text = yaml.dump(ci_workflow_data)
    assert "secrets." not in text, "CI must not read repository secrets"


def test_ci_no_release_write(ci_workflow_data: dict) -> None:
    text = yaml.dump(ci_workflow_data)
    assert "release" not in text.lower(), "CI must not create releases"



def _collect_service_env(compose_data: dict, service_name: str) -> dict[str, str]:
    service = compose_data["services"][service_name]
    env_raw = service.get("environment", {})
    result: dict[str, str] = {}
    if isinstance(env_raw, dict):
        result.update({str(k): str(v) for k, v in env_raw.items()})
    elif isinstance(env_raw, list):
        for item in env_raw:
            if isinstance(item, str):
                if "=" in item:
                    key, _, val = item.partition("=")
                    result[key.strip()] = val.strip()
            elif isinstance(item, dict):
                result.update({str(k): str(v) for k, v in item.items()})
    return result
