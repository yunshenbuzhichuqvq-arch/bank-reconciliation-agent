# ADR-27.1: 可复现交付采用五服务 Compose 与零外部凭证默认路径

**Slug**: `five-service-compose-zero-credential-default`
**Status**: accepted
**Date**: 2026-07-11

## Context

Stage 27 需要让全新环境能够以一条 Compose 命令启动并验证项目。当前仓库没有
`Dockerfile`、`frontend/Dockerfile` 或 `compose.yaml`，API、ARQ worker、MySQL、Redis 和前端仍依赖
开发者分别启动。路线图原先将 Compose 概括为 backend、frontend、MySQL、Redis 四个服务，但现有
异步上传契约由独立 ARQ worker 消费 Redis 队列；省略 worker 无法证明 Stage 25 的终态恢复和现有
异步链路，把 Uvicorn 与 worker 塞入同一容器又会混淆进程退出、日志和重启语义。

历史 ADR-005 与 ADR-26.1 已确定 Fake provider 是默认、零密钥、network-free 的确定性路径，真实
DeepSeek 只能显式 opt-in；现有 hash embedding 也能避免默认下载真实模型。Stage 27 必须延续这些
边界，同时不能把本地演示 Compose 描述为生产部署。

## Options Considered

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

## Decision

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

## Consequences

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
