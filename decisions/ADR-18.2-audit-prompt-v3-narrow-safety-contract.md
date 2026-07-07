# ADR-18.2: 使用窄范围 Audit Prompt v3 安全契约，不做泛化模型调参

**Slug**: `audit-prompt-v3-narrow-safety-contract`
**Status**: accepted
**Date**: 2026-07-07

## Context

确定性安全闸是必要条件，但不应是唯一改进。`prompts/audit_v2.md` 在输出 schema 中允许 `AUTO_FIXED`，且没有给 `DUPLICATE_BOOKING`、`BE-R008` 或必须复核分支提供显式决策规则。DeepSeek 很可能把金额相等加 evidence 理解成可以自动平账，但重复记账本身是高风险异常。

本 stage 应降低模型产生 unsafe output 的概率，但不能把问题扩展成大范围模型调参。

## Options Considered

- Option A: 只加确定性安全策略，不改 prompt。优点：运行时安全最强，prompt 变更最小。缺点：模型可能继续输出 unsafe raw decision，每次安全通过都依赖策略介入。
- Option B: 为所有分支加入大量 few-shot。优点：可能整体改善模型行为。缺点：prompt 变长、token 成本更高、维护更复杂，也更容易对 6 个 eval case 过拟合。
- Option C: 新增紧凑的 Audit Prompt v3，写清 branch-level 安全规则，few-shot 扩展暂不做。优点：精准针对已测失败，改动小且容易 review。缺点：prompt 服从性仍不保证，必须由 ADR-18.1 兜底。

## Decision

采用 Option C。

Audit Prompt v3 应显式写清决策边界：

- 对 `task=audit`，异常分支是审计发现，不是直接结算授权。
- `BE-R008 / DUPLICATE_BOOKING` 必须输出 `PENDING_HUMAN`，风险为 `HIGH`，并建议挂起或人工复核，不得自动平账。
- 金额相等不能覆盖重复记账风险。
- RAG evidence 只能支持 reason，不能单独授予 auto-fix 权限。
- `AUTO_FIXED` 只在任务契约明确允许时可用，例如既有 `task=confirm_match` 候选确认路径。

Prompt 变更应新增版本文件，不覆盖旧 prompt 历史。这样 `prompt_version`、prompt 对比和报告元数据仍可追踪。

## Consequences

- 正向：模型在进入确定性安全闸之前能看到更清晰的安全契约。
- 正向：变更足够窄，可以和旧 DeepSeek 报告做可解释对比。
- 正向：prompt versioning 保持 `prompt_version` 可追溯。
- 负向：真实 provider 非确定性仍可能导致 prompt 失效。
- 负向：更严格的 prompt 可能降低边界 case 的自动化率，尤其是未来若出现候选确认以外的可自动平账 eval case。
- 约束：本 stage 不切换模型、不新增依赖、不引入 LLM-as-Judge。
