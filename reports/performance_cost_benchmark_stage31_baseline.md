# Stage 31 Trace-Guided Performance Benchmark

```json
{
  "schema_version": "1.0",
  "stage": "stage-31-trace-guided-performance",
  "artifact_role": "baseline",
  "evaluated_at": "2026-07-14T01:28:46.866097Z",
  "git_revision": "7c4b0a7d13f6ab437cbbb0a20815980bbf944214",
  "input_sha256": "1f4c2ccf28d6deccfe31caac3b01737aa842f351bc75fe847ff2a89c067233a3",
  "environment": {
    "os": "Darwin",
    "architecture": "arm64",
    "python": "3.11.15",
    "boundary": "offline benchmark; not production SLA"
  },
  "provider": {
    "requested_provider": "deepseek",
    "effective_provider": "deepseek",
    "requested_model": "deepseek-v4-flash",
    "effective_model": "deepseek-v4-flash"
  },
  "rag": {
    "requested_embedding_backend": "bge_m3",
    "effective_embedding_backend": "bge_m3",
    "retrieval_mode": "dense"
  },
  "run_plan": {
    "cold_runs": 1,
    "warmup_runs": 1,
    "measured_runs": 20,
    "complete_measured_count": 20
  },
  "trust": {
    "trusted": true,
    "reasons": [],
    "environment_gap": null
  },
  "trace": {
    "completeness_numerator": 20,
    "completeness_denominator": 20,
    "completeness_rate": 1.0,
    "samples": [
      {
        "trace_id": "fea1da4b-9be1-4182-b65b-0b256d4c536e",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "9c75a350-1f69-4493-890a-7ff8b279071c",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "f17fe584-584e-48c5-81da-1cda332c6729",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "a0ac6379-432b-47e3-908d-9a534e071503",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "dfd38267-6fac-41d7-ada8-b452d521618c",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "dc9036da-b989-48ba-aa50-c0422b905222",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "9cc7c049-9e8d-4c81-9edb-c86a35ba7cad",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "f16241f1-1dbf-481a-8754-40dd5298a949",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "9f44fdd8-d84c-48a8-9fd8-34a27e2ba1a1",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "7e6cec99-bbe1-417f-9884-ffbb85831012",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "f5c6c5ef-9b13-42f9-b2a5-56d57dce9d7a",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "a486bb0b-7f39-4b55-925a-14c5aab2b0a1",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "c97c8f4c-515b-430b-9d8a-bc421ec13d0e",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "454aa882-bcc9-4714-9bf6-dbd88230f1d5",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "c45ce308-b7fd-436d-b8bb-7783fc60d773",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "3b98403a-bc9a-44b5-b691-5a851610b962",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "aeab987b-649f-4c2e-849b-65f5ce132f31",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "768e7ce2-2ae0-4b4f-bfe6-e45b8a2a36c7",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "6cdf5041-7919-45e3-8746-4e98f670403b",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "74d8ede8-4fe9-4d0f-b279-db389f3ba049",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      }
    ]
  },
  "latency": {
    "cold_observations": [
      {
        "e2e_ms": 17166.942,
        "extraction_ms": 3156,
        "rag_ms": 6907
      }
    ],
    "end_to_end": {
      "avg_latency_ms": 8500.346,
      "p50_latency_ms": 7915.476,
      "p95_latency_ms": 20400.707,
      "min_latency_ms": 5388.518,
      "max_latency_ms": 20400.707,
      "samples_ms": [
        8097.964,
        8658.283,
        7651.769,
        9726.563,
        8220.969,
        20400.707,
        8242.92,
        7272.785,
        10404.315,
        10584.463,
        8546.924,
        7523.942,
        10453.384,
        6086.584,
        7430.029,
        7732.988,
        5764.826,
        5751.572,
        5388.518,
        6067.412
      ]
    },
    "extraction_agent": {
      "avg_latency_ms": 2694.05,
      "p50_latency_ms": 2229.5,
      "p95_latency_ms": 5498,
      "min_latency_ms": 1492,
      "max_latency_ms": 5498,
      "samples_ms": [
        1707,
        2042,
        3200,
        1635,
        2766,
        5498,
        4657,
        1641,
        2761,
        4866,
        2417,
        3024,
        2975,
        1817,
        3536,
        1975,
        1914,
        2036,
        1492,
        1922
      ]
    },
    "rag_search": {
      "avg_latency_ms": 70.65,
      "p50_latency_ms": 70.5,
      "p95_latency_ms": 74,
      "min_latency_ms": 66,
      "max_latency_ms": 74,
      "samples_ms": [
        66,
        71,
        72,
        69,
        73,
        72,
        71,
        70,
        73,
        69,
        68,
        73,
        71,
        74,
        68,
        70,
        70,
        74,
        69,
        70
      ]
    }
  },
  "theory": {
    "per_run_predicted_parallel_e2e_ms": [
      8031.964,
      8587.283,
      7579.769,
      9657.563,
      8147.969,
      20328.707,
      8171.92,
      7202.785,
      10331.315,
      10515.463,
      8478.924,
      7450.942,
      10382.384,
      6012.584,
      7362.029,
      7662.988,
      5694.826,
      5677.572,
      5319.518,
      5997.412
    ],
    "actual_warm_p95_ms": 20400.707,
    "predicted_warm_p95_ms": 20328.707,
    "theoretical_p95_improvement_pct": 0.353,
    "formula": "actual_e2e_ms - extraction_duration_ms - rag_duration_ms + max(extraction_duration_ms, rag_duration_ms)"
  },
  "independence": {
    "data_dependency": {
      "finding": "safe",
      "detail": "RAG query is built from scenario_type, error_type, exception_branch, and amounts via _build_rag_query(); does not read extraction_result. Static code analysis confirms data independence.",
      "source": "static_code_analysis"
    },
    "shared_state": {
      "finding": "safe",
      "detail": "In serial runtime there is no concurrent access. For a parallel candidate, this assessment is conditional on workers receiving read-only inputs and returning results without modifying shared ReconciliationState, Trace recorder, SSE emitter, or persistent state. This has NOT been verified in running code.",
      "source": "static_analysis_unverified"
    },
    "failure_order": {
      "finding": "bounded",
      "detail": "In serial runtime, Extraction failure causes early return before RAG. In a parallel candidate, the failure of one side while the other is in-flight requires explicit fail-closed handling. This has NOT been verified in running code; the analysis assumes both sides are guarded.",
      "source": "static_analysis_unverified"
    },
    "cancellation": {
      "finding": "bounded",
      "detail": "Synchronous provider/retriever calls may not support hard interrupt. A thread pool must use bounded timeouts and guarantee no background state mutation after timeout. This has NOT been verified in running code.",
      "source": "static_analysis_unverified"
    },
    "resource_reclamation": {
      "finding": "safe",
      "detail": "Thread pool context manager guarantees resource release on exit. This assessment is conditional on proper implementation.",
      "source": "static_analysis_unverified"
    }
  },
  "usage": {
    "logical_agent_calls": 40,
    "logical_tool_calls": 24,
    "provider_transport_attempts": 40,
    "input_tokens": 58960,
    "output_tokens": 15293,
    "total_tokens": 74253,
    "per_successful_run_tokens": 3712
  },
  "cost": {
    "assumptions": "DeepSeek v4 Pro pricing: input $0.89/1M, output $3.45/1M",
    "total_estimated_usd": "0.03895251",
    "per_successful_run_estimated_usd": "0.0019476255",
    "unavailable_reason": null
  },
  "reliability": {
    "success_count": 20,
    "failure_count": 0,
    "error_rate": 0.0,
    "error_distribution": {}
  },
  "decision": "no_go",
  "closed_reasons": [
    "theory_pct_0.353_lt_20.0"
  ]
}
```

## Baseline Decision
**Decision**: `no_go`
**Reasons**: ['theory_pct_0.353_lt_20.0']

## Identity
- Schema: `1.0`
- Stage: `stage-31-trace-guided-performance`
- Git: `7c4b0a7d13f6ab437cbbb0a20815980bbf944214`
- Input SHA256: `1f4c2ccf28d6deccfe31caac3b01737aa842f351bc75fe847ff2a89c067233a3`

## Trust
- Trusted: `True`
- Reasons: []

## Run Plan
- Cold: 1
- Warmup: 1
- Measured: 20
- Complete: 20

## Latency
- E2E P95: 20400.707 ms
- E2E P50: 7915.476 ms

## Theory
- Predicted P95: 20328.707 ms
- Actual P95: 20400.707 ms
- Improvement: 0.353%

## Usage
- Provider calls: 0
- Total tokens: 74253

## Cost
- Total: 0.03895251
- Per-run: 0.0019476255

## Reliability
- Success: 20
- Failure: 0
- Error Rate: 0.0

## Independence Gate
- **data_dependency**: `safe` — RAG query is built from scenario_type, error_type, exception_branch, and amounts via _build_rag_query(); does not read extraction_result. Static code analysis confirms data independence.
- **shared_state**: `safe` — In serial runtime there is no concurrent access. For a parallel candidate, this assessment is conditional on workers receiving read-only inputs and returning results without modifying shared ReconciliationState, Trace recorder, SSE emitter, or persistent state. This has NOT been verified in running code.
- **failure_order**: `bounded` — In serial runtime, Extraction failure causes early return before RAG. In a parallel candidate, the failure of one side while the other is in-flight requires explicit fail-closed handling. This has NOT been verified in running code; the analysis assumes both sides are guarded.
- **cancellation**: `bounded` — Synchronous provider/retriever calls may not support hard interrupt. A thread pool must use bounded timeouts and guarantee no background state mutation after timeout. This has NOT been verified in running code.
- **resource_reclamation**: `safe` — Thread pool context manager guarantees resource release on exit. This assessment is conditional on proper implementation.
