from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


RUNS = 5


def _measure_ms(fn) -> float:
    started = time.perf_counter()
    fn()
    return (time.perf_counter() - started) * 1000


def _average_ms(samples: list[float]) -> float:
    return statistics.mean(samples) if samples else 0.0


def main() -> int:
    from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent
    from bank_reconciliation_agent.core.config import settings
    from bank_reconciliation_agent.core.llm.provider import get_llm_provider
    from bank_reconciliation_agent.rag.retriever import rule_retriever
    from bank_reconciliation_agent.schemas.rag import RagSearchRequest

    provider = get_llm_provider()
    extraction_agent = ExtractionAgent(provider=provider)
    extraction_samples = [
        _measure_ms(
            lambda: extraction_agent.extract(
                flow_id="FLOW-BENCH-001",
                summary="冲正退款备注待核验",
                remark="原流水疑似冲正，需要抽取原始流水号",
            )
        )
        for _ in range(RUNS)
    ]
    rag_request = RagSearchRequest(
        query="银行企业对账 冲正 摘要不一致 规则",
        top_k=3,
        scenario_type="BANK_ENTERPRISE",
    )
    rag_samples = [_measure_ms(lambda: rule_retriever.search(rag_request)) for _ in range(RUNS)]

    extraction_avg = _average_ms(extraction_samples)
    rag_avg = _average_ms(rag_samples)
    ratio = extraction_avg / rag_avg if rag_avg > 0 else float("inf")

    print("Agent latency benchmark for ADR-032")
    print(f"runs={RUNS}")
    print(f"provider={settings.llm_provider} model={getattr(provider, 'model', 'unknown')}")
    print(f"ExtractionAgent average_ms={extraction_avg:.3f} samples_ms={extraction_samples}")
    print(f"RAG average_ms={rag_avg:.3f} samples_ms={rag_samples}")
    print(f"ratio extraction_over_rag={ratio:.2f}x")
    if settings.llm_provider == "fake":
        print("Note: fake provider benchmark; ExtractionAgent latency here is not representative of a real LLM.")
        print("Note: with a real provider, ExtractionAgent is commonly ~1-3s while local RAG is often <100ms.")

    if ratio >= 1.0:
        print(
            "Conclusion: measured ratio shows ExtractionAgent is slower than or equal to RAG, "
            "which supports ADR-032 keeping the workflow serial."
        )
    else:
        print(
            "Conclusion: measured ratio shows ExtractionAgent is faster than RAG in this run; "
            "interpret fake-provider numbers cautiously before revisiting ADR-032."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
