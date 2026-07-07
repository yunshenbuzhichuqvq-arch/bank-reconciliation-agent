# Performance & Cost Benchmark

## Metadata

| Key | Value |
|---|---|
| Run Count | 5 |
| Provider Requested | `fake` |
| Provider Effective | `fake` |
| Model Requested | `deepseek-v4-flash` |
| Model Effective | `fake-llm` |
| Evaluated At | 2026-07-07T10:10:07.347082Z |

## Latency

| Component | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Samples (ms) |
| --- | ---: | ---: | ---: | ---: | --- |
| ExtractionAgent | 0.062 | 0.108 | 0.040 | 0.108 | 0.066, 0.108, 0.057, 0.04, 0.04 |
| RAG Search | 49.342 | 243.564 | 0.707 | 243.564 | 243.564, 0.88, 0.782, 0.779, 0.707 |

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
| 1 | 0.066 | 243.564 |
| 2 | 0.108 | 0.88 |
| 3 | 0.057 | 0.782 |
| 4 | 0.04 | 0.779 |
| 5 | 0.04 | 0.707 |
