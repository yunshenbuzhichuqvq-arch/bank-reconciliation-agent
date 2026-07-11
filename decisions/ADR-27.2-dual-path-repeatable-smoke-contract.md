# ADR-27.2: Smoke 采用 ARQ 与 SSE 双路径并输出可重复的机器可读结果

**Slug**: `dual-path-repeatable-smoke-contract`
**Status**: accepted
**Date**: 2026-07-11

## Context

Stage 27 路线图要求 smoke 按真实认证契约覆盖登录、上传、任务执行、SSE/状态、异常、人工复核和报告，
并要求连续运行两次。当前运行时存在两条有意分离的路径：`upload-async` 把任务交给 Redis/ARQ worker，
但不会注册进程内 SSE emitter；`upload → start-live → events` 能验证现有 SSE，却不经过 ARQ worker。
Stage 27 若强行把两者合成一条链路，将需要改变事件持久化或跨进程传输架构，超出可复现交付范围。

任务 ID 又由上传内容寻址生成。若 smoke 第二次只读取第一次留下的 `COMPLETED`，脚本可能假成功而没有
重新验证 worker；若两条路径复用同一组内容，它们还会竞争同一个 task 状态。因此 smoke 必须显式定义
双路径、受控样例、force requeue、有限超时和稳定失败语义。

## Options Considered

- **Option A：一个外部 smoke 顺序执行 ARQ 异步路径和 SSE 路径（采纳）**
  - Pros：能从容器外同时证明 JWT、API、MySQL、Redis、worker、SSE、人工复核与报告；保持现有 API
    contract 不变；失败可定位到真实跨服务步骤。
  - Cons：需要两组受控样例；执行时间较长；重复运行、复核写入和内容寻址任务状态的测试维护成本
    较高。
- **Option B：只验证 `upload-async`，用状态轮询代替 SSE**
  - Pros：一条任务链即可覆盖队列和 worker；脚本较短，状态冲突较少。
  - Cons：不能证明 README 中的 `start-live → events` 入口；SSE 路径仍可能在交付配置中失效。
- **Option C：使用 TestClient 或 mock 替代外部 HTTP/Compose smoke**
  - Pros：速度快、故障注入容易、无需启动全部容器。
  - Cons：不能证明 Compose DNS、JWT、真实 MySQL/Redis、worker 进程和端口暴露可用；与“一键复现”
    目标不符。

## Decision

采用 **Option A**。

- `scripts/smoke_demo.py` 作为容器外黑盒客户端，首先检查 backend readiness，再调用真实
  `/api/v1/auth/login` 获取 JWT；后续业务请求全部携带 Bearer token，不保留已废弃的 `X-User-ID`
  演示契约。
- ARQ 路径固定为
  `upload-async(force=true) → Redis/ARQ worker → 有限超时状态轮询 → exceptions → pending review → approve → report`。
  `force=true` 必须使第二次 smoke 重新入队，而不是把遗留终态当作本次成功。
- SSE 路径固定为
  `upload → start-live → events → TASK_DONE → status → report`。SSE 继续使用当前进程内 emitter；
  本 Stage 不增加跨进程事件总线、事件持久化或回放能力。
- 两条路径使用不同的仓库内受控样例，避免内容寻址 `task_id` 相互覆盖。具体文件、scenario 与预期
  终态由 `spec.md` 冻结；样例必须稳定产生 smoke 所需的异常和至少一个可执行复核项，不得伪造 API
  响应。
- 每一步必须具有有限 timeout 和稳定机器可读 step name，至少区分 `readiness`、`auth`、
  `async_upload`、`queue_completion`、`exceptions`、`review`、`report`、`sync_upload`、`sse_terminal`。
  基础设施不可用、终态失败、响应 schema 不符或超时均 fail closed。
- 脚本结束时输出版本化 JSON summary，至少包含 `schema_version`、`success`、有效 Fake/hash 边界、
  task IDs、每步 outcome/duration 和最终失败步骤。全部成功返回 0；任一步失败仍尽力输出 summary 并
  返回非零。
- summary、标准输出和错误输出不得包含 JWT、密码、API key、认证头、数据库/Redis 完整连接串、完整
  上传内容或不必要的财务明细。
- 连续两次运行是正式验收契约：第二次必须实际重走 force requeue 与 SSE 初始化，同时不得因缓存、
  已审批记录、残留任务或命名冲突失败。

## Consequences

- 正向：smoke 能以真实跨服务调用证明五服务拓扑和当前两条运行路径，不把单元测试或 mock 包装成部署
  证据。
- 正向：版本化 summary、稳定步骤名和非零退出码可以被本地 DoD 与 GitHub Actions 共同消费，失败点
  可审查。
- 负向：双路径 smoke 比单探针慢，并与受控样例、内容寻址幂等、force requeue 和人工复核状态紧密
  耦合；相关 contract 演进时必须同步脚本与测试。
- 负向：smoke 会产生真实演示数据和复核写入；清理策略或重复运行语义错误时，可能留下难以解释的
  环境状态。
- 负向：当前 SSE 仍是进程内、非持久化链路；本 smoke 只能证明单 backend 实例下的实时事件，不能
  证明断线回放或水平扩展。
- 约束：本决策不建设跨进程 SSE、Trace replay、负载测试、故障恢复演练或生产合成监控。
