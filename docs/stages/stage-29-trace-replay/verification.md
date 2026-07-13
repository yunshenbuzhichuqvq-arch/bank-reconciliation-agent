# Stage 29 Verification: TraceSpan 与任务回放

**Stage**: `stage-29-trace-replay`
**Branch**: `stage-29-trace-replay`
**Status**: local-closeout-complete
**Verdict**: Approve
**Last Updated**: 2026-07-13

## Verification Boundary

- 本记录对应本地 `stage-29-trace-replay` 分支，最终实现 commit 为 `f3ceb33`。
- Stage 29 只提供 observation replay；不重新执行 Tool、RAG、LLM、Guard 或业务写入。
- evidence 环境为 Fake provider、hash embedding、file-backed local SQLite，不代表真实 DeepSeek、
  真实 embedding、生产 SLA 或集群可用性。
- 本地收尾不包含 push、GitHub PR 或 merge；远程发布仍由用户执行。

## Task Completion Summary

| Task | Implementation Commit(s) | Review | Status |
| --- | --- | --- | --- |
| TASK-29.1 | `bea2f11` | approved after repair loop | done |
| TASK-29.2 | `f5fa5d4` | approved after repair loop | done |
| TASK-29.3 | `ae1840d` | approved after repair loop | done |
| TASK-29.4 | `82aa1ab` | approved after repair loop | done |
| TASK-29.5 | `76c28a1` | approved after repair loop | done |
| TASK-29.6 | `c1be039` | approved after repair loop | done |
| TASK-29.7 | `06272da` | approved after evidence rebuild | done |
| TASK-29.8 | `cd17ac4` | approved after fact review | done |
| TASK-29.9 | `770ab15` | approved | done |
| TASK-29.10 | `0074d86` | approved after TASK-29.15 | done |
| TASK-29.11 | `7295388` | approved after TASK-29.15 | done |
| TASK-29.12 | `daf39b1` | approved after TASK-29.15 | done |
| TASK-29.13 | `14a50fe` | approved | done |
| TASK-29.14 | `9a7bbff` | approved | done |
| TASK-29.15 | `2ef56e5`, `9ff2902`, `f3ceb33` | approved | done |

## Stage / PR Gate

- [x] `uv run pytest` — passed: `1108 passed, 1 skipped, 6 warnings` in `202.56s`。
- [x] `uv run ruff check .` — passed。
- [ ] `uv run ruff format --check .` — inherited baseline failure: `94 files would be
  reformatted, 110 files already formatted`。
  - Stage 29 分支改动涉及的 Python 文件中，23 个通过；6 个失败。
  - 这 6 个文件在 `main` 对应版本上逐一复验也全部失败，因此没有 Stage 29 新增的 format regression。
  - `TASK-29.15` 明确禁止在本 Stage 扩大为 repo-wide format 治理；本地收尾接受该 baseline exception。
- [x] `cd frontend && npm run test` — passed: `18 files, 61 tests`。
- [x] `cd frontend && npm run typecheck` — passed。
- [x] `cd frontend && npm run build` — passed；仅有既有 dynamic-import 与 bundle-size warnings。
- [x] `git diff --check` — passed。

## Trace Evidence Gate

- [x] runner 第一次隔离执行 — process exited `0`。
- [x] runner 第二次隔离执行 — process exited `0`。
- [x] 两次稳定字段一致：scenario set/order、pass verdict、claim、numerator/denominator、
  error/fallback distribution 与 token aggregate 均一致。
- [x] `scenario_pass_count=6/6`。
- [x] Trace completeness 为真实 `5/6`；故意注入 Trace 写失败的 eligible execution 保留在 denominator。
- [x] tracked JSON 与 Markdown 同口径：`6/6`、`5/6`。
- [x] report forbidden-token scan — passed。
- [x] 非 SQLite、非 hash 或启用 RAG feature flag 的环境在项目服务导入前 fail-fast，且不覆盖旧报告。

## Runtime and Contract Gate

- [x] TraceSpan schema、snapshot invariants、SQLAlchemy/MySQL DDL parity 和 SQLite persistence tests 通过。
- [x] caller/span `user_id + task_id + flow_id` identity mismatch 被拒绝。
- [x] Replay latest/history、稳定 tie-break、`AVAILABLE/IN_PROGRESS/TRACE_NOT_AVAILABLE` 和 non-leaking
  tenant 404 语义通过。
- [x] Tool/Agent span 在真实调用前分配 identity/start time；异常完成同一 span 后保持原传播语义。
- [x] `AUTO_FIXED/PENDING_HUMAN/UNRESOLVED` terminal truth 与 FALLBACK schema rejection 通过。
- [x] SSE 与持久化 span identity 集合一致；root/terminal 各一次，无重复。
- [x] projection、event construction、emitter 三类 SSE 故障不影响 ledger、queue、task stats、
  recorder snapshot 或 Trace persistence。
- [x] structured repair、真实 Replay HTTP cross-tenant denial、真实业务 Trace-write failure isolation
  evidence 通过。
- [ ] 真实 MySQL/Compose fresh volume 与 existing volume DDL replay — 本轮未运行；当前证据来自
  schema parity tests 与 SQLite。该项保留为部署前环境验证，不包装为已验证生产能力。

## Frontend and Documentation Gate

- [x] Ledger detail → Replay 路由、latest/history/loading/error/not-available states 通过。
- [x] route param reactivity、request ownership、URL encoding 和 stale-response protection 通过。
- [x] evidence IDs 只读、可键盘操作和复制，不加载正文。
- [x] README、PRD、architecture 已同步数据库 Trace、Replay API、SSE v1.2、离线证据与
  Business `TraceAgent` / Execution Trace 边界。
- [x] 旧 JSON Trace 与 `TRACE_DIR` 已移除。

## Git and Publication Gate

- [x] 当前分支不是 `main`。
- [x] 本地 `origin/main` 是当前 HEAD 的 ancestor；分支相对本地 `origin/main` ahead `17` commits。
- [x] `git ls-files ADR.md` 为空，根目录不存在 scratch `ADR.md`。
- [x] branch diff 未包含 `.env`、缓存或前端构建产物；`.env.example` 仅删除废弃 `TRACE_DIR`。
- [x] 三份 accepted ADR 和 Stage 29 `spec.md/tasks.md/verification.md` 已准备为正式 tracked artifacts。
- [ ] formal Stage/ADR artifacts commit — pending user commit。
- [ ] remote push — not run。
- [ ] GitHub PR / merge — not run。

## Remaining Non-blocking Boundaries

- repo-wide Ruff format baseline 需要独立治理，不在 Stage 29 扩大范围。
- Trace 为 append-only，Stage 29 不提供 TTL、自动清理或删除 API；真实生产前需要数据保留策略。
- SSE 仍是单进程实时通道，不提供 `Last-Event-ID`、断点续传或跨实例广播。
- 真实 MySQL/Compose DDL replay 和生产部署 smoke 尚未执行。

## Final Verdict

**Approve.** TASK-29.1–29.15 全部完成，Stage 29 本地实现与验证收尾完成。待用户提交六份正式
Stage/ADR artifacts 后，可执行：

```bash
git push -u origin stage-29-trace-replay
```

然后在 GitHub 创建 `base=main`、`compare=stage-29-trace-replay` 的 PR。
