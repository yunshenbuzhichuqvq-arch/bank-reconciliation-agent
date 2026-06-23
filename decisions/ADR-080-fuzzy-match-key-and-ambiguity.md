# ADR-080: 模糊匹配键与一对多歧义处理

**Stage**: stage-recon-hardening
**Status**: accepted
**Date**: 2026-06-22
**Slug**: `fuzzy-match-key-and-ambiguity`

## Context

架构 §2.3.1 阶段2 键为 amount 相等 ∧ date 相等 ∧ `counterparty LIKE`。两侧对手方字段不同名(`_bank_party_column` / `_clear_party_column`,承 ADR-015/016 场景化列映射)。模糊配对可能一对多(同金额、同日、对手方近似的多笔),确定性层若强行 1:1 配对会赌错,污染下游。

## Decision

匹配键为 amount 相等 ∧ date 相等 ∧ 对手方 LIKE(复用现有场景化列映射);**唯一候选才配对**,出现多候选时,涉及行全部标 `FUZZY_MATCH_CANDIDATE` 转 AuditAgent,不在确定性层选「哪一笔配哪一笔」。符合「金额/状态不交给不确定逻辑」「无依据转人工」红线(ADR-016);确定性层只做能确定的事。LIKE 的具体归一化(掩码/子串口径)为实现细节。

## Consequences

- 负向:多候选不自动配对 → 这类样本进 Agent/人工,自动平账率略降(诚实代价,自动化率不虚高)。
- 正向:确定性层零误配,所有模糊判定可追溯到 Agent 决策与证据。

## Alternatives Considered

- **确定性层按相似度评分取最优 1:1**(贪心配对):相似度阈值/打分本身引入不确定性,等于在确定性层做了「该交给 Agent 的语义判断」,违背 §2.3 边界,错配难追溯。否决。
