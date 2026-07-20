from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from functools import partial
from threading import BoundedSemaphore, Lock
from typing import Callable

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.reconciliation_types import (
    ReconciliationFlowBundle,
    ReconciliationMatchResult,
    ReconciliationWriteBundle,
)
from bank_reconciliation_agent.services.stream_emitter import StreamEmitter


FlowBuilder = Callable[..., ReconciliationFlowBundle]

_EXECUTOR_LOCK = Lock()
_executor: ThreadPoolExecutor | None = None
_ADMISSION_LOCK = Lock()
_admission_gate: BoundedSemaphore | None = None


def get_reconciliation_executor() -> ThreadPoolExecutor:
    """Return the process-wide flow executor, separate from the Tool executor."""

    global _executor
    with _EXECUTOR_LOCK:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.reconciliation_max_concurrency,
                thread_name_prefix="reconciliation-flow",
            )
        return _executor


def get_reconciliation_admission_gate() -> BoundedSemaphore:
    """Return the process-wide cap shared by executor and direct flow paths."""

    global _admission_gate
    with _ADMISSION_LOCK:
        if _admission_gate is None:
            _admission_gate = BoundedSemaphore(settings.reconciliation_max_concurrency)
        return _admission_gate


def build_write_bundle(
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
    results: list[ReconciliationMatchResult],
    build_flow: FlowBuilder,
    emitter: StreamEmitter | None = None,
) -> ReconciliationWriteBundle:
    pending_results = [result for result in results if result.status != "AUTO_FIXED"]
    if (
        emitter is not None
        or settings.reconciliation_max_concurrency == 1
        or len(pending_results) <= 1
    ):
        flow_bundles: list[ReconciliationFlowBundle] = []
        stream_seq = 0
        for result in pending_results:
            flow_bundle = build_flow_bundle_with_admission(
                result,
                user_id=user_id,
                task_id=task_id,
                scenario_type=scenario_type,
                build_flow=build_flow,
                emitter=emitter,
                stream_seq_start=stream_seq,
            )
            stream_seq = flow_bundle.stream_seq
            flow_bundles.append(flow_bundle)
    else:
        admitted_build = partial(
            build_flow_bundle_with_admission,
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            build_flow=build_flow,
            emitter=None,
            stream_seq_start=0,
        )
        executor = get_reconciliation_executor()
        futures = [executor.submit(admitted_build, result) for result in pending_results]
        flow_bundles = ordered_flow_results(futures)

    return merge_flow_bundles(flow_bundles)


def build_flow_bundle_with_admission(
    result: ReconciliationMatchResult,
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
    build_flow: FlowBuilder,
    emitter: StreamEmitter | None,
    stream_seq_start: int,
) -> ReconciliationFlowBundle:
    gate = get_reconciliation_admission_gate()
    with gate:
        return build_flow(
            result,
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            emitter=emitter,
            stream_seq_start=stream_seq_start,
        )


def ordered_flow_results(
    futures: list[Future[ReconciliationFlowBundle]],
) -> list[ReconciliationFlowBundle]:
    """Join one batch completely, then return results in router order."""

    try:
        return [future.result() for future in futures]
    except BaseException:
        for future in futures:
            future.cancel()
        wait(futures)
        raise


def merge_flow_bundles(
    flow_bundles: list[ReconciliationFlowBundle],
) -> ReconciliationWriteBundle:
    return ReconciliationWriteBundle(
        ledger_rows=[bundle.ledger_row for bundle in flow_bundles],
        rag_log_rows=[bundle.rag_log_row for bundle in flow_bundles],
        agent_log_rows=[bundle.agent_log_row for bundle in flow_bundles],
        trace_snapshots=[
            bundle.trace_snapshot
            for bundle in flow_bundles
            if bundle.trace_snapshot is not None
        ],
        ai_processed_rows=len(flow_bundles),
        fallback_l2_rows=sum(bundle.fallback_l2_rows for bundle in flow_bundles),
        fallback_l3_rows=sum(bundle.fallback_l3_rows for bundle in flow_bundles),
        total_prompt_tokens=sum(bundle.prompt_tokens for bundle in flow_bundles),
        total_completion_tokens=sum(bundle.completion_tokens for bundle in flow_bundles),
        saved_prompt_tokens=sum(bundle.saved_prompt_tokens for bundle in flow_bundles),
        saved_completion_tokens=sum(bundle.saved_completion_tokens for bundle in flow_bundles),
    )
