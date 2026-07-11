# ADR-27.3: Hosted CI 使用独立检查并从本次提交重建确定性评测证据

**Slug**: `hosted-ci-fresh-deterministic-evidence`
**Status**: accepted
**Date**: 2026-07-11

## Context

仓库已有完整 pytest/Ruff、前端 test/typecheck/build、三层 offline eval harness 与 Stage 24 分层 gate，
但没有 `.github/workflows/*`。当前 `scripts/eval_gates.py` 可以直接读取仓库内报告；如果实现变化后报告
没有刷新，Hosted CI 只消费静态 JSON 会产生“代码已变、旧报告仍 pass”的假绿。另一方面，Stage 17、
21、23、24 已明确区分 default Fake/hash CI evidence、真实 DeepSeek/embedding 的 opt-in diagnostic 和
release trust，Stage 27 不得为了 Hosted CI 模糊这些边界。

Compose 与 smoke 也是本 Stage 的交付产物。若它们只在编写时手工验证而不进入 PR check，后续代码或
依赖变化可能让 Dockerfile 和容器网络悄然失效。CI 需要在可定位性、证据 freshness 与运行时间之间取
最小但真实的平衡。

## Options Considered

- **Option A：四个独立 PR checks，fresh deterministic eval 与 Compose smoke 均进入 CI（采纳）**
  - Pros：后端、前端、评测和容器交付分别可见；评测输入与当前 commit 绑定；Dockerfile/Compose
    漂移能在 PR 阶段被发现；不同检查可以合理并行或按成本排序。
  - Cons：workflow 和 artifact 管理更复杂；Compose build、MySQL/Redis 拉取和双 smoke 显著增加
    CI 时长；GitHub runner/Docker Hub 瞬时问题会扩大外部失败面。
- **Option B：三个检查，仅运行 backend、frontend 与 deterministic eval，Compose smoke 只做本地 DoD**
  - Pros：PR CI 更快、更稳定；减少镜像下载和容器资源消耗。
  - Cons：本 Stage 的核心交付链路不受 Hosted CI 保护；容器文件可能在后续 PR 中失效而不被发现。
- **Option C：所有命令合并为一个串行 job**
  - Pros：workflow 配置短；环境和缓存只初始化一次。
  - Cons：失败定位差；前后端不能并行；GitHub PR 无法独立展示质量、评测与交付状态；慢步骤会阻塞
    所有反馈。

## Decision

采用 **Option A**。

- `.github/workflows/ci.yml` 在 `pull_request` 与人工 `workflow_dispatch` 上运行；默认 token 权限收敛为
  `contents: read`，不在 workflow 中写入仓库、创建 release 或调用外部业务系统。
- PR checks 固定分为：
  - `backend-quality`：按 `uv.lock` 安装 Python 依赖，运行完整 `pytest` 与 `ruff check .`。
  - `frontend-quality`：使用 `npm ci`，运行 `npm run test`、`npm run typecheck`、`npm run build`。
  - `deterministic-eval`：在本次 job 内重新生成 Fake provider + hash embedding harness comparison 与
    Agent schema conformance，再运行 `scripts/eval_gates.py`。
  - `delivery-smoke`：构建五服务 Compose，等待健康状态，连续运行 `scripts/smoke_demo.py` 两次，并在
    结束时始终清理 containers、networks 与测试 volumes。
- `deterministic-eval` 的 blocking 输入必须由当前 commit 在当前 job 内生成；不得复制或仅校验已提交的
  `reports/eval_harness/comparison.json` 与 `reports/agent_schema_conformance.json`。生成结果写入 CI 临时
  目录或 runner 工作区，并作为本次运行的诊断 artifact，不回写 Git history。
- default PR 只以 Stage 24 gate 的 CI layer 为阻断依据。真实 DeepSeek、真实 embedding 与真实 provider
  cost report 缺失时继续显示为 manual/release environment gap；不得使用
  `--fail-on-release-block` 让这些 opt-in 证据阻断默认 PR。
- CI 显式使用 `LLM_PROVIDER=fake` 与 `EMBEDDING_BACKEND=hash`，不得读取模型 secret、调用真实
  DeepSeek、下载真实 embedding 或运行 cost benchmark。Fake/hash 结果不得标记为真实模型或真实语义
  检索证据。
- `delivery-smoke` 在较快的质量与 eval checks 通过后运行，以避免明显失败时浪费容器构建资源；失败时
  上传机器可读 smoke summary 和完成脱敏的必要容器日志，清理步骤使用 always-run 语义。
- workflow 使用锁文件支持的确定性安装路径；GitHub Action、Python、Node、MySQL 与 Redis 的精确版本
  由 `spec.md` 冻结，避免在 ADR 中固化局部 YAML 细节。
- README、`system-prd.md` 与 `overall-architecture.md` 必须同步当前事实和 claim boundary：JWT、SSE、
  ARQ/Redis 已实现；主工作流是 plain Python，LangGraph 只用于 HumanReview checkpoint 子图；当前
  Reranker 不是 Cross-Encoder；Hosted CI 只证明离线 Fake/hash 确定性边界。

## Consequences

- 正向：每个 PR 都能独立证明代码质量、前端构建、评测 freshness 和实际容器链路，旧静态报告不能再
  单独制造 CI pass。
- 正向：真实 diagnostic 缺失不会破坏默认 CI 的零凭证属性，同时 release trust 仍保持 fail closed，
  不把 environment gap 包装成真实质量证据。
- 负向：四个 jobs、fresh harness、Compose build 与双 smoke 会增加 CI 配置量、运行时间、缓存需求和
  artifact 管理成本。
- 负向：Hosted CI 依赖包注册表、GitHub runner、Docker daemon 与基础镜像拉取；这些外部故障可能造成
  与业务代码无关的失败，需要日志明确区分。
- 负向：fresh harness 的生成参数、输出路径和 gate 输入形成新的交付契约，评测脚本变化时必须同步
  workflow，否则会 fail closed。
- 约束：本决策不引入真实模型 CI、真实 embedding CI、定时夜间任务、release 自动化、云部署、生产
  secret 管理或 SLA 声明。
