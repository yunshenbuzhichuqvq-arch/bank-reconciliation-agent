# Performance & Cost Benchmark

## Metadata

| Key | Value |
|---|---|
| Run Count | 5 |
| Provider Requested | `fake` |
| Provider Effective | `fake` |
| Model Requested | `deepseek-v4-flash` |
| Model Effective | `fake-llm` |
| Evaluated At | 2026-07-07T10:04:22.666036Z |

## Latency

| Component | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Samples (ms) |
| --- | ---: | ---: | ---: | ---: | --- |
| ExtractionAgent | 0.063 | 0.110 | 0.042 | 0.110 | 0.062, 0.11, 0.06, 0.043, 0.042 |
| RAG Search | 32.755 | 160.644 | 0.750 | 160.644 | 160.644, 0.866, 0.762, 0.751, 0.75 |

## Token Usage

| Key | Value |
|---|---|
| Token Usage Available | False |

## Cost

| Key | Value |
|---|---|
| Cost Available | False |
| Assumptions | fake provider; no real LLM cost |

## Claim Boundary

- offline benchmark; not production SLA
- **Not real LLM latency**: fake provider; ExtractionAgent latency here does not represent a real LLM.
- **No real LLM cost**: fake provider; cost data is not available.

## Per-Run Latency

| Run | ExtractionAgent (ms) | RAG Search (ms) |
| ---: | ---: | ---: |
| 1 | 0.062 | 160.644 |
| 2 | 0.11 | 0.866 |
| 3 | 0.06 | 0.762 |
| 4 | 0.043 | 0.751 |
| 5 | 0.042 | 0.75 |
