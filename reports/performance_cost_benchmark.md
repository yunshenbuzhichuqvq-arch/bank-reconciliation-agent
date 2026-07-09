# Performance & Cost Benchmark

## Metadata

| Key | Value |
|---|---|
| Run Count | 5 |
| Provider Requested | `deepseek` |
| Provider Effective | `deepseek` |
| Model Requested | `deepseek-v4-flash` |
| Model Effective | `deepseek-v4-flash` |
| Evaluated At | 2026-07-09T07:45:52.133525Z |

## Latency

| Component | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Samples (ms) |
| --- | ---: | ---: | ---: | ---: | --- |
| ExtractionAgent | 3312.742 | 4661.419 | 1493.089 | 4661.419 | 3240.832, 4495.113, 2673.257, 4661.419, 1493.089 |
| RAG Search | 1308.533 | 6278.735 | 59.224 | 6278.735 | 6278.735, 59.224, 68.768, 67.165, 68.774 |

## Token Usage

| Key | Value |
|---|---|
| Token Usage Available | True |
| Input Tokens | 1115 |
| Output Tokens | 1105 |
| Total Tokens | 2220 |

## Cost

| Key | Value |
|---|---|
| Cost Available | True |
| Estimated Cost (USD) | 0.001446375 |
| Per Case Estimated Cost (USD) | 0.000289275 |
| Assumptions | DeepSeek v4 Pro pricing: input $0.435/1M, output $0.87/1M |

## Claim Boundary

- offline benchmark; not production SLA

## Per-Run Latency

| Run | ExtractionAgent (ms) | RAG Search (ms) |
| ---: | ---: | ---: |
| 1 | 3240.832 | 6278.735 |
| 2 | 4495.113 | 59.224 |
| 3 | 2673.257 | 68.768 |
| 4 | 4661.419 | 67.165 |
| 5 | 1493.089 | 68.774 |
