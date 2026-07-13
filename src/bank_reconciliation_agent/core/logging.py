import logging
import sys
from typing import Any

import structlog


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def bind_trace_context(
    *,
    trace_id: str,
    user_id: str,
    thread_id: str,
    task_id: str | None = None,
    flow_id: str | None = None,
) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        user_id=user_id,
        thread_id=thread_id,
    )
    if task_id is not None:
        structlog.contextvars.bind_contextvars(task_id=task_id)
    if flow_id is not None:
        structlog.contextvars.bind_contextvars(flow_id=flow_id)


log: Any = structlog.get_logger()

# Context-free structured logger for safe Tool attempt observations. It shares the
# stdlib logging handler (same output stream) but deliberately excludes
# ``merge_contextvars`` so request-scoped fields such as ``trace_id``/``user_id``/
# ``thread_id`` never merge into Tool attempt records. It does not disable the
# global processor chain or clear the bound context, so normal logs keep them.
tool_observation_log: Any = structlog.wrap_logger(
    logging.getLogger("bank_reconciliation_agent.tool_observation"),
    processors=[structlog.processors.JSONRenderer()],
    wrapper_class=structlog.stdlib.BoundLogger,
)
