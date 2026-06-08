# ADR-008: structlog 结构化日志 + Prompt 版本治理

- Status: Accepted (2026-06-08)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: system-prd.md §3.3, overall-architecture.md(可观测性), t_agent_execution_log.prompt_version

## Context

PRD §3.3 要求:所有 LLM 调用点输出 JSON 日志(带 `trace_id / user_id / thread_id / agent_name / step / prompt_version`);现有 `print`/`logging` 全换 structlog;Prompt 落独立文件版本化;`t_agent_execution_log.prompt_version` 可溯源;附 Prompt 版本对比脚本。可观测性是大模型应用的工程核心(overall-architecture:可观测性从 MVP-2a 起)。

## Options

观测层:
1. **structlog(PRD 指定),JSON renderer + contextvars 绑定 trace 字段** — PRD 对齐、结构化可被日志系统消费、contextvars 自动透传,代价是新依赖、需统一改造现有日志点。
2. **标准 logging + json formatter** — 无新依赖,但手工拼字段易漏、偏离 PRD。

Prompt 管理:
3. **Prompt 存 `prompts/*.md`,文件名带版本(`audit_v1.md`),loader 读取并回传 version** — 版本化、可 diff、可溯源、与代码解耦,代价是多一层加载、版本号手维护。
4. **Prompt 内联为代码常量** — 简单,但不可独立版本化/对比,违反 PRD。

## Decision

观测取 **Option 1**、Prompt 取 **Option 3**。
- 新增依赖 `structlog>=24.0.0`;封装 `core/logging.py` 配 JSON renderer + contextvars(`trace_id/user_id/thread_id`);LLM 调用点与编排节点统一结构化 `log.info(event, agent_name=..., step=..., prompt_version=...)`。
- 现有 `print`/`logging` 调用点替换为 structlog——仅限本阶段触及的 agent / 编排 / provider 模块,不顺手改无关模块(surgical)。
- Prompt 文件落 `prompts/`(`extraction_v1.md` / `audit_v1.md` / `trace_v1.md`;`rewrite_v1` 留 2a-2)。`prompts/loader.py` 按名加载、回传 `prompt_version`(取文件名版本段)。
- `t_agent_execution_log.prompt_version` 记录每次决策所用版本。
- Prompt 版本对比脚本 `scripts/compare_prompts.py`:同批 mock 数据用不同版本各跑一次,对比 `decision` 一致性与 `confidence` 分布(Fake 下产出确定性结果;真实漂移需 live)。

## Consequences

- 正面:LLM 决策全程可溯源(`trace_id` 串一次任务、`prompt_version` 锚定提示词);Prompt 可独立演进与对比。
- 负向:新增 structlog 依赖面;全量替换日志点有一次性改造量(限定范围);Prompt 版本号手维护,改 Prompt 须新建文件并更新 loader 映射;对比脚本在 Fake 下只验证管线,真实漂移要 live。
