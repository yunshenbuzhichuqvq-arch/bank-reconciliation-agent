# Stage Faker Mock Data — Architectural Decisions

> Scratchpad(tracked,PR 前按 CLAUDE.md §4.2 删除,不进 main)。
> 收尾拆进 `decisions/` 时按仓库实际惯例编**全局连续号**(当前最高 ADR-089 → 本 stage 为 ADR-090/091/092-<slug>.md),非 CLAUDE.md 示例里的 `<stage>.<seq>` 编号。

## ADR-FK.1: 原地保守 Faker 化现有对账 mock 生成器
**Slug**: `mock-data-in-place-conservative-faker`
**Status**: accepted
**Date**: 2026-06-24

### Context
`scripts/generate_mock_excel.py` 的三个生成器(`generate_mock_excel` / `generate_mvp1_mock_excel` / `generate_mvp2a3_mock_excel`)所有字段均为手写字面量,装饰字段(银行名、网点名等)重复、玩具感强。`EXPECTED_BRANCHES` / `BANK_CLEARING_EXPECTED_BRANCHES` 是人工编排的场景骨架,被 20+ 个测试文件直接 import 并断言「flow_id → 异常分支」。PRD §11.1 要求模拟数据「结果可复现,每类样本有明确预期识别结果」。目标:提升**非场景字段**真实感,同时不破坏确定性、不动场景与断言。

### Options Considered
- **A. 新增独立 Faker 生成器,旧 fixture 不动** — Pros: 现有 fixture/断言零回归;可顺带放大数据规模。Cons: 旧 fixture 玩具感原样保留;多一套并行数据资产、维护面变大;没解决「现有 e2e 数据不真实」。
- **B. 原地保守:仅 Faker 可证无关的装饰字段,场景字段全冻结(采纳)** — Pros: 直接改善现有 e2e/demo 数据真实感;改动面小、外科手术式;以「既有断言零改全绿」做自动红线。Cons: 安全可填面小(见 FK.3),真实感提升有限。
- **C. 原地激进:连对手方名称/摘要/账号一并 Faker** — Pros: 真实感最大。Cons: 名称/摘要/账号参与匹配与「名称不符/重复入账」判定,须把值断言改成结构式 + 逐场景核对不变量,回归面大,task 从小升中。

### Decision
采用 **B**。在三个现有生成器内,把装饰字段取值从字面量替换为 seeded Faker 输出;`flow_id`、各金额、日期/时间、摘要、对手方名称及其关系、`_enrich_*` 派生字段一律冻结。可填字段边界见 FK.3,确定性机制见 FK.2。红线由「现有 ~20 断言测试零改动全绿」自动执法。

### Consequences
- 负向:可安全 Faker 的字段仅一小撮(主要银行名/网点/终端等标签),「玩具感」只去一部分;用户已知此局限并接受。
- 负向:Faker 误碰场景字段会让既有测试变红——这是预期的护栏行为,处置是把该字段**回收进冻结集**,而非改测试迁就。
- 现有 e2e fixture 与 demo 数据就地变真实,无并行数据资产;列结构不变,`reconciliation` 列校验(承 ADR-019)零影响。

---

## ADR-FK.2: 确定性——每生成器入口重置 Faker 种子
**Slug**: `mock-faker-per-generator-seed-reset`
**Status**: accepted
**Date**: 2026-06-24

### Context
PRD §11.1 要求可复现。测试各自独立调用单个生成器(`generate_mvp1_mock_excel(tmp_path)` 等),也有测试在一个用例里连调多个生成器。Faker 默认实例的输出依赖累计抽取次数:若仅在模块级 seed 一次,同一生成器的输出会随「之前抽过多少次 / 调用顺序」漂移,破坏可复现与跨测试稳定。

### Options Considered
- **A. 模块级全局 seed 一次** — Pros: 最少代码。Cons: 输出依赖调用顺序与累计抽取数,单个生成器非自含可复现,跨测试不稳定,引入隐性 flaky。
- **B. 每个生成器函数入口 `Faker.seed(<固定常量>)` 重置(采纳)** — Pros: 每个生成器自含、与调用顺序无关、逐次可复现;契合「测试独立调用单个生成器」现状。Cons: 三处各重置(可共用一个种子常量)。
- **C. 不 seed,接受随机** — Pros: 最真实。Cons: 直接违反 PRD §11.1 可复现,任何值断言立刻 flaky。排除。

### Decision
采用 **B**:每个生成器函数开头用固定种子常量重置 Faker,使输出与调用顺序/次数无关、逐次一致。

### Consequences
- 每个生成器输出确定、可复现,满足 PRD §11.1;新增一条「同生成器连跑两次输出逐字段相等」的确定性测试守护。
- 负向:同进程内重复调用同一生成器会得到完全相同的装饰值(对固定 fixture 是期望行为,但意味着 Faker 不提供跨调用多样性)。

---

## ADR-FK.3: 引入 faker 依赖 + 显式 fillable 白名单护栏
**Slug**: `faker-dep-and-explicit-fillable-allowlist`
**Status**: accepted
**Date**: 2026-06-24

### Context
需要真实中文公司/银行名 → 选 Faker(`zh_CN`)。但字段红线极易踩错:看似无关的「ID 类」字段里,`voucher_no` / `reference_no` / `merchant_order_no` 是 BC-R003 跨日切**候选匹配键**(承 ADR-017/019,须两侧单号贯通),`*_serial_no` / 账号掩码可能参与匹配或幂等。须有可审计、可静态核对的边界,而非埋在散落赋值里。`faker` 仅服务 `scripts/` + 测试,不进运行时 `src/`。

### Options Considered
- **依赖选型**:
  - **A. 引入 `faker`(dev/test extra,`zh_CN`)(采纳)** — Pros: 现成高质量中文语料;只进 dev/test 不污染运行时。Cons: 多一个 dev 依赖 + `uv.lock` 更新。
  - **B. 自写极简随机生成器** — Pros: 零新依赖。Cons: 重造轮子、中文语料质量差,YAGNI。
  - **C. 用 stdlib `random` 拼名** — Cons: 名称不真实,失去本 stage 意义。
- **红线落地**:
  - **D. 仅靠测试套件兜底** — Pros: 零额外代码。Cons: 红线隐式,reviewer 看不出哪些字段是「有意允许」;新增字段时易越界。
  - **E. 显式 `FAKER_FILLABLE_FIELDS` 白名单常量 + 测试兜底(采纳)** — Pros: 可填字段在代码里集中、命名、可审计;Faker 只许写白名单内字段;测试套件 + 确定性测试做安全网。Cons: 多维护一份常量。

### Decision
引入 `faker`(dev/test extra,`zh_CN`);定义显式 `FAKER_FILLABLE_FIELDS` 白名单,Faker **仅允许写白名单字段**。**默认冻结**(不入白名单):`voucher_no` / `reference_no` / `merchant_order_no`(承 ADR-017/019 候选匹配键)、`bank_serial_no` / `clearing_serial_no`、各账号掩码——凡参与匹配/幂等/未经证实者一律不入白名单(保守优先)。初版白名单倾向纯标签字段(银行名、网点名、终端号等),具体成员由 Codex 在「既有测试零改全绿」约束下逐一确认入选。

### Consequences
- 红线在代码中显式可审计;reviewer 与未来改动可一眼看出 Faker 允许的字段集。
- 负向:`faker` 新增 dev 依赖,需更新 `pyproject.toml` + `uv.lock`;白名单随字段演进需维护。
- 负向:为安全把多数 ID 类字段排除在外,Faker 实际覆盖面小(与 FK.1 局限一致)。
