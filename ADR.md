# Stage 27 — Architectural Decisions

## ADR-27.1: 可复现交付采用五服务 Compose 与零外部凭证默认路径

**Slug**: `five-service-compose-zero-credential-default`
**Status**: accepted
**Date**: 2026-07-11

### Context

Stage 27 需要让全新环境能够以一条 Compose 命令启动并验证项目。当前仓库没有
`Dockerfile`、`frontend/Dockerfile` 或 `compose.yaml`，API、ARQ worker、MySQL、Redis 和前端仍依赖
开发者分别启动。路线图原先将 Compose 概括为 backend、frontend、MySQL、Redis 四个服务，但现有
异步上传契约由独立 ARQ worker 消费 Redis 队列；省略 worker 无法证明 Stage 25 的终态恢复和现有
异步链路，把 Uvicorn 与 worker 塞入同一容器又会混淆进程退出、日志和重启语义。

历史 ADR-005 与 ADR-26.1 已确定 Fake provider 是默认、零密钥、network-free 的确定性路径，真实
DeepSeek 只能显式 opt-in；现有 hash embedding 也能避免默认下载真实模型。Stage 27 必须延续这些
边界，同时不能把本地演示 Compose 描述为生产部署。

### Options Considered

- **Option A：backend、worker、frontend、MySQL、Redis 五服务，backend/worker 复用镜像（采纳）**
  - Pros：API 与 worker 各自只有一个主进程；能独立观察、重启和健康检查；同一 Python 镜像保证代码
    与依赖一致；Compose 可以真实覆盖 Redis/ARQ 路径。
  - Cons：服务数由路线图字面上的四个增加到五个；health dependency、日志和启动顺序配置更复杂；
    构建与拉取镜像耗时增加。
- **Option B：四服务，并在 backend 容器中同时启动 Uvicorn 与 ARQ worker**
  - Pros：保持四服务表述；只需一个后端容器。
  - Cons：需要 shell 编排或额外进程管理器；任一子进程退出时容器状态可能仍显示正常；日志、信号、
    重启和健康检查语义含混；引入 Stage 27 不需要的新运行时复杂度。
- **Option C：四服务，但省略 worker，只演示同步 API**
  - Pros：Compose 最简单；启动资源和 smoke 时长较低。
  - Cons：无法证明异步上传、Redis 队列、ARQ retry/terminal recovery 已可交付；与 Stage 27 的真实
    运行时事实同步目标冲突。

### Decision

采用 **Option A**。

- Compose 拓扑固定为 `backend`、`worker`、`frontend`、`mysql`、`redis` 五个服务。
- `backend` 与 `worker` 使用同一个由 `uv.lock` 构建的 Python 镜像，但以不同 command 分别运行
  Uvicorn 与 `arq bank_reconciliation_agent.worker.WorkerSettings`；不得在单容器中并行托管两个
  长驻主进程，也不新增 supervisor 类依赖。
- MySQL 与 Redis 使用各自原生 healthcheck；backend 与 worker 均仅在 MySQL、Redis ready 后启动。
  worker 的存活检查复用 ARQ 0.28 已提供的 `--check` CLI，不新增健康检查服务。
- frontend 使用 Node 多阶段构建，并以 `vite preview --host 0.0.0.0` 提供已构建静态产物。该入口仅
  定位为本地可复现演示，不声明为生产 Web Server；本 Stage 不引入 Nginx 或新的静态服务器依赖。
- frontend 在开发服务器与 preview 中继续通过 Vite proxy 把 `/api` 转发到 backend；容器浏览器流量
  不直接跨域访问 backend，也不为 Compose 增加 CORS。具体 proxy 配置字段由 `spec.md` 冻结。
- Compose 默认显式设置 `LLM_PROVIDER=fake`、`EMBEDDING_BACKEND=hash`、
  `ASYNC_QUEUE_ENABLED=true`，并把容器内 MySQL/Redis 地址指向 Compose service name。默认路径不得
  需要 DeepSeek key、真实 embedding 模型下载或其他业务外部凭证。
- JWT demo secret 与 demo password 可以提供明确标记为 non-production 的本地演示默认值；真实值只能
  通过环境变量覆盖。密钥、认证头和连接凭据不得写入镜像层、源码或 CI artifact。
- `.env.example` 负责列出当前代码已实现的 JWT、Redis、异步队列、缓存、限流、checkpoint、
  embedding、ARQ 与 Stage 26 LLM 治理配置；Compose 只提供能完成确定性演示的有限默认覆盖，不复制
  第二套配置模型。
- 容器健康只证明本地演示依赖可用，不形成生产 readiness、容量、可用性或安全合规声明。

### Consequences

- 正向：API、worker、MySQL、Redis 与前端具有清晰、可独立验证的进程边界，且异步链路不再依赖宿主机
  手工启动的隐藏进程。
- 正向：Fake/hash 默认路径延续既有可信边界，在无模型密钥、无模型下载的环境中仍可启动和 smoke。
- 负向：五服务拓扑比原路线图的四服务描述更复杂，Compose build、healthcheck 调试和 CI 资源消耗都会
  增加。
- 负向：`vite preview` 只适合演示；未来若进入正式部署，仍需单独决策静态资源服务器、TLS、反向代理
  和安全响应头。
- 负向：本地 non-production 凭证虽然降低演示门槛，也可能被误用于非本地环境，因此文档与启动日志
  必须持续提示覆盖凭证。
- 约束：本决策不引入 Nginx、Kubernetes、云资源、服务网格、新进程管理器、生产 SLA 或完整监控平台。

## ADR-27.2: Smoke 采用 ARQ 与 SSE 双路径并输出可重复的机器可读结果

**Slug**: `dual-path-repeatable-smoke-contract`
**Status**: accepted
**Date**: 2026-07-11

### Context

Stage 27 路线图要求 smoke 按真实认证契约覆盖登录、上传、任务执行、SSE/状态、异常、人工复核和报告，
并要求连续运行两次。当前运行时存在两条有意分离的路径：`upload-async` 把任务交给 Redis/ARQ worker，
但不会注册进程内 SSE emitter；`upload → start-live → events` 能验证现有 SSE，却不经过 ARQ worker。
Stage 27 若强行把两者合成一条链路，将需要改变事件持久化或跨进程传输架构，超出可复现交付范围。

任务 ID 又由上传内容寻址生成。若 smoke 第二次只读取第一次留下的 `COMPLETED`，脚本可能假成功而没有
重新验证 worker；若两条路径复用同一组内容，它们还会竞争同一个 task 状态。因此 smoke 必须显式定义
双路径、受控样例、force requeue、有限超时和稳定失败语义。

### Options Considered

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

### Decision

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

### Consequences

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

## ADR-27.3: Hosted CI 使用独立检查并从本次提交重建确定性评测证据

**Slug**: `hosted-ci-fresh-deterministic-evidence`
**Status**: accepted
**Date**: 2026-07-11

### Context

仓库已有完整 pytest/Ruff、前端 test/typecheck/build、三层 offline eval harness 与 Stage 24 分层 gate，
但没有 `.github/workflows/*`。当前 `scripts/eval_gates.py` 可以直接读取仓库内报告；如果实现变化后报告
没有刷新，Hosted CI 只消费静态 JSON 会产生“代码已变、旧报告仍 pass”的假绿。另一方面，Stage 17、
21、23、24 已明确区分 default Fake/hash CI evidence、真实 DeepSeek/embedding 的 opt-in diagnostic 和
release trust，Stage 27 不得为了 Hosted CI 模糊这些边界。

Compose 与 smoke 也是本 Stage 的交付产物。若它们只在编写时手工验证而不进入 PR check，后续代码或
依赖变化可能让 Dockerfile 和容器网络悄然失效。CI 需要在可定位性、证据 freshness 与运行时间之间取
最小但真实的平衡。

### Options Considered

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

### Decision

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

### Consequences

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
