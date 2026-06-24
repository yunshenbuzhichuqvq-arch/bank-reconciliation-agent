# ADR-090: 模拟数据按真实对账批次重建(取代原地保守装饰)

> 归档自 stage faker-mock-data(scratchpad 原编号 ADR-FK.1)。本 stage 决策归档为 ADR-090(FK.1)/091(FK.2)/092(FK.3)/093(FK.4)/094(FK.5);正文 `ADR-FK.x` 即同 stage 决策,对应 ADR-(089+x)。

**Slug**: `mock-data-realistic-reconciliation-batch`
**Status**: accepted(supersedes 初版 in-place-conservative,commit 4d06856)
**Date**: 2026-06-24

### Context
银企对账真实流:企业会计带来本企业某周期(~两周)的**企业账**(Source A);对公经理从行内系统调出该企业**同期银行流水**(Source B)。确定性引擎匹配,**绝大多数自动平账、不调 LLM**;只有少数异常(金额差 / 单边 / 重复 / 名称不符 / 跨日切)进 agent → 才真正调 LLM。数据应是一个**对账批次**:正常多数 + 异常少数。初版把现有 8 行异常 fixture 当「数据本体」、只给边角字段刷 Faker,既不建模这个批次结构,又让摘要等叙述字段保持模板化——而叙述字段恰是 LLM 价值所在。故重建。

### Options Considered
- **A. 原地保守装饰(初版,已 superseded)** — 只给边角字段刷 Faker、冻结约 20 个场景字段。Pros: 零回归。Cons: 不建模真实批次;摘要等叙述字段仍模板化、藏住 LLM 核心价值;实测把字段多样性塌成单值(行级 seed 粒度 bug)。
- **B. 新增独立真实生成器、旧的全保留** — Pros: 旧测试零改。Cons: 两套数据资产并存,旧 toy 数据继续误导 demo;关注点分散。
- **C. 重建为真实对账批次(采纳)** — 三个生成器内部重写为「正常多数成对生成→自动平账 + 异常少数注入→落分支」;对外签名保留为 scenario 包装。Pros: 数据逼近真实;演示「确定性多数 + LLM 少数」分流;摘要等叙述字段成为一等真实目标。Cons: 中等重建;需改造硬编码「数据集身份」的测试断言(集合 / 计数 / 字面量)。

### Decision
采用 **C**。正确性模型见 ADR-091、叙述真实化见 ADR-092、生成器形态见 ADR-093、测试改造见 ADR-094。

### Consequences
- 负向:scope 从「小 stage」升为「中等重建」,断言改造面真实存在。
- 正向:mock 数据贴近真实银企对账批次;demo 能呈现「N 笔零 LLM 自动平账 + M 笔异常各触发 agent」的成本分流(接 LLM 省本/指标线)。
- 初版的 `FAKER_FILLABLE_FIELDS` 白名单冻结机制不再需要(正确性改为结构性,见 ADR-091)。

### 实现落地(TASK-FK.1~4)
`scripts/generate_mock_excel.py` 内部重写为「正常成对(`_normal_bank_enterprise_rows` / `_normal_bank_clearing_rows`)+ 异常注入(`_bank_enterprise_anomaly_rows` / `_bank_clearing_anomaly_rows`)」;三个生成器(`generate_mock_excel` / `generate_mvp1_mock_excel` / `generate_mvp2a3_mock_excel`)退化为薄包装,签名与列契约不变。重生成的 6 个 xlsx 行数为 18/17(银企)、14/16(清算),= 12 正常 + 异常子集,经审查与生成器逐字段一致。
