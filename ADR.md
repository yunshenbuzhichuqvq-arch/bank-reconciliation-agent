# Stage Faker Mock Data — Architectural Decisions (rebuild)

> Scratchpad(tracked,PR 前按 CLAUDE.md §4.2 删除,不进 main)。
> 本版**取代**初版「原地保守装饰」决策(已 commit 4d06856,见 FK.1 Options A);初版细节留 git 历史。
> 收尾拆进 `decisions/` 编全局连续号(当前最高 ADR-089 → 本 stage 顺接)。

## 背景(业务流,贯穿全部决策)
银企对账真实流:企业会计带来本企业某周期(~两周)的**企业账**(Source A);对公经理从行内系统调出该企业**同期银行流水**(Source B)。确定性引擎匹配,**绝大多数自动平账、不调 LLM**;只有少数异常(金额差 / 单边 / 重复 / 名称不符 / 跨日切)进 agent → 才真正调 LLM。初版把现有 8 行异常 fixture 当「数据本体」、只给边角字段刷 Faker,既不建模这个批次结构,又让摘要等叙述字段保持模板化——而叙述字段恰是 LLM 价值所在。故重建。

---

## ADR-FK.1: 模拟数据按真实对账批次重建(取代原地保守装饰)
**Slug**: `mock-data-realistic-reconciliation-batch`
**Status**: accepted(supersedes 初版 in-place-conservative,commit 4d06856)
**Date**: 2026-06-24

### Context
见上「业务流」。数据应是一个**对账批次**:正常多数 + 异常少数。

### Options Considered
- **A. 原地保守装饰(初版,已 superseded)** — 只给边角字段刷 Faker、冻结约 20 个场景字段。Pros: 零回归。Cons: 不建模真实批次;摘要等叙述字段仍模板化、藏住 LLM 核心价值;实测把字段多样性塌成单值(行级 seed 粒度 bug)。
- **B. 新增独立真实生成器、旧的全保留** — Pros: 旧测试零改。Cons: 两套数据资产并存,旧 toy 数据继续误导 demo;关注点分散。
- **C. 重建为真实对账批次(采纳)** — 三个生成器内部重写为「正常多数成对生成→自动平账 + 异常少数注入→落分支」;对外签名保留为 scenario 包装。Pros: 数据逼近真实;演示「确定性多数 + LLM 少数」分流;摘要等叙述字段成为一等真实目标。Cons: 中等重建;需改造硬编码「数据集身份」的测试断言(集合 / 计数 / 字面量)。

### Decision
采用 **C**。正确性模型见 FK.2、叙述真实化见 FK.3、生成器形态见 FK.4、测试改造见 FK.5。

### Consequences
- 负向:scope 从「小 stage」升为「中等重建」,断言改造面真实存在。
- 正向:mock 数据贴近真实银企对账批次;demo 能呈现「N 笔零 LLM 自动平账 + M 笔异常各触发 agent」的成本分流(接 LLM 省本/指标线)。
- 初版的 `FAKER_FILLABLE_FIELDS` 白名单冻结机制不再需要(正确性改为结构性,见 FK.2)。

---

## ADR-FK.2: 正确性=结构性;EXPECTED_BRANCHES 作异常子集;确定性在生成器入口
**Slug**: `structural-correctness-anomaly-subset-and-determinism`
**Status**: accepted(revises 初版 FK.2 的「每生成器入口重置 seed」,扩为正确性模型)
**Date**: 2026-06-24

### Context
重建后正确性的根基变了:不再逐字段对字面量,而是「正常对两侧按构造一致 → 自动平账;异常按构造注入 → 落预期分支」。需重新定义测试断言依据,并守住可复现(PRD §11.1)。

### Options Considered
- **正确性判据**:
  - **A. 逐字段字面量断言(初版路径)** — Cons: 与「放开 Faker 造真实多样数据」互斥,逼出冻结一切。
  - **B. 结构性断言(采纳)** — 正常行应全 `AUTO_FIXED` + 异常子集各落预期分支 + 异常计数。`EXPECTED_BRANCHES` / `BANK_CLEARING_EXPECTED_BRANCHES` **保留,语义=「被标注的异常子集」**,批次其余为正常多数。Pros: 允许真实多样数据;断言更具业务意义(防形式修复);多数 call-site 不变。Cons: 需改写硬编码「全集 / 计数」的断言。
- **确定性粒度**:
  - **A. 行级 helper 重置 seed(初版实现的 bug)** — 实测使同生成器每行抽到相同值、多样性塌成单值。排除。
  - **B. 仅生成器入口重置(采纳)** — draw 在批次内累积 → 行间多样;整批逐次可复现。

### Decision
正确性=结构性;`EXPECTED_BRANCHES` 作异常子集;固定 seed **仅在生成器入口**重置(显式禁止在行级 helper 重置)。

### Consequences
- 负向:需逐个识别并改写硬编码全集 / 计数的断言(见 FK.5)。
- 正向:断言贴业务语义;消除初版的多样性塌缩;批次可复现。

---

## ADR-FK.3: 叙述字段(摘要 / 附言 / remark)真实化 = 人工策划 seeded 三档池
**Slug**: `narrative-fields-curated-seeded-pool`
**Status**: accepted(replaces 初版 FK.3 的「faker 依赖 + 白名单」)
**Date**: 2026-06-24

### Context
摘要 / 附言是自由文本,正是确定性规则啃不动、**必须 LLM 上场**的地方(模糊摘要结构化、对手方与用途的语义判断,PRD §3.2;BE-R004 名称 / 叙述不符)。模板化摘要(现状 `remark="MVP-1 自动平账样例"`)会把 LLM 价值藏起来。纯 Faker 文本是无意义中文,给不了金融语义。

### Options Considered
- **A. 纯 Faker text** — Cons: 无意义、非金融语义,达不到目的。
- **B. LLM 生成摘要** — Pros: 最真实。Cons: 数据生成引入 LLM 成本 + 不确定性,违可复现;过度。
- **C. 人工策划 seeded 三档摘要池 + Faker 填实体(采纳)** — 三档:正式规范 / 口语化 / 歧义缺信息。Pros: 领域真实、可复现、零运行成本;异常案例配歧义档,逼出 LLM 推理价值。Cons: 维护一份语料。

### Decision
采用 **C**。正常行从正式 / 口语档采样;异常行(尤其 NARRATIVE_NAME_MISMATCH)配歧义 / 口语摘要,与注入异常对齐。实体字段(公司名 / 账号 / 银行名)仍由 Faker 生成。

### Consequences
- 负向:新增一份策划摘要语料需维护。
- 正向:摘要真实多样、含口语与歧义,demo 中 LLM 的「读懂模糊叙述」价值可见。

---

## ADR-FK.4: scenario 参数化的批次生成器 + 规模可配
**Slug**: `scenario-parameterized-batch-generator`
**Status**: accepted
**Date**: 2026-06-24

### Context
现有三个生成器(legacy 银企 / mvp1 银企 / mvp2a3 清算)各自硬编码全部行。重建应共享一套「批次核心」,按 scenario 决定字段映射 / 异常集 / 摘要档,承 ADR-015(单场景引擎 Source A/B 抽象)、ADR-019(列契约 `BANK/CLEAR_REQUIRED_COLUMNS` 复用,不引 scenario-keyed 校验)。

### Options Considered
- **A. 三个生成器各自全量重写** — Cons: 批次 / 平账 / 注入逻辑重复三份,易漂移。
- **B. 共享批次核心 + scenario 参数 + 三个生成器为薄包装(采纳)** — 单一批次逻辑;`bank_enterprise` / `bank_clearing` 决定字段、异常集、摘要;保留三个对外签名 → call-site 不动。Pros: 逻辑单点;承既有场景抽象;churn 受控。Cons: 须把场景差异抽成参数。
- **规模**:`n_normal` 参数化(默认每场景 ~50 正常 + 既有异常集);测试传小值、demo 传大值 → 真实感与测试速度解耦(现 9.6s 不被拖垮)。

### Decision
采用 **B** + `n_normal` 参数化。faker 依赖(dev/`zh_CN`)保留,用于实体字段生成。列契约 / 函数签名不变(承 ADR-019)。

### Consequences
- 负向:批次核心需吸收三场景差异,初次抽象有成本。
- 正向:单点维护;新增场景只加参数;测试与 demo 共用一套、规模解耦。

---

## ADR-FK.5: 测试改造策略——保调用点,只改集合 / 计数 / 字面量断言
**Slug**: `test-rework-keep-callsites-restructure-assertions`
**Status**: accepted
**Date**: 2026-06-24

### Context
~20 个测试 import 生成器 / `EXPECTED_BRANCHES`。重建后多数 call-site(取数据集 → 遍历异常子集断言分支)**不变**;但少数硬编码「数据集 == 全集 / `len == N` / `summary == 某字面量`」的断言,会因正常多数加入 + 摘要真实化而失效。

### Options Considered
- **A. 全量重写测试** — Cons: 回归面最大、丢失既有覆盖、易引入新错。
- **B. 保调用点、定向改断言(采纳)** — 「== 全集」改「异常子集 ⊆ 结果 且其余 `AUTO_FIXED`」;字面量摘要断言改结构 / 关系断言;计数按 `n_normal + 异常数`。**新增**:正常多数自动平账断言、异常计数断言、字段多样性守护(堵初版盲区)。Pros: 保留覆盖、改动定向可审。Cons: 须逐文件识别受影响断言。

### Decision
采用 **B**。受影响断言逐处改为结构 / 子集 / 计数断言;补正常平账 + 异常计数 + 多样性守护测试。

### Consequences
- 负向:需逐文件核对受影响断言,Codex 须在 Report Back 列出所有被改测试与改法。
- 正向:测试更贴业务语义、防形式修复、防多样性回归;调用点保稳定。
