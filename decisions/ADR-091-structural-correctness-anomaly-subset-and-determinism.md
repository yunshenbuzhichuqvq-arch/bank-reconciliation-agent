# ADR-091: 正确性=结构性;EXPECTED_BRANCHES 作异常子集;确定性在生成器入口

> 归档自 stage faker-mock-data(scratchpad 原编号 ADR-FK.2)。本 stage 决策归档为 ADR-090(FK.1)/091(FK.2)/092(FK.3)/093(FK.4)/094(FK.5);正文 `ADR-FK.x` 即同 stage 决策,对应 ADR-(089+x)。

**Slug**: `structural-correctness-anomaly-subset-and-determinism`
**Status**: accepted(revises 初版 FK.2 的「每生成器入口重置 seed」,扩为正确性模型)
**Date**: 2026-06-24

### Context
重建后正确性的根基变了:不再逐字段对字面量,而是「正常对两侧按构造一致 → 自动平账;异常按构造注入 → 落预期分支」。需重新定义测试断言依据,并守住可复现(PRD §11.1)。初版实现还埋了一个 bug:固定 seed 在**行级 helper** 重置,使同生成器每行抽到相同值、字段多样性塌成单值。

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
- 负向:需逐个识别并改写硬编码全集 / 计数的断言(见 ADR-094)。
- 正向:断言贴业务语义;消除初版的多样性塌缩;批次可复现。

### 实现落地(TASK-FK.2)
seed 仅在 `build_batch` 入口经 `_reset_batch_faker(seed)` 重置;正常行 loop 复用同一 faker 实例累积抽样(`faker.company()` / `street_name()` / `sample_narrative(...)`),行间多样。新增 `test_mock_batches_keep_field_diversity`(`nunique > 1` 守护,堵初版盲区)与 `test_build_batch_is_deterministic_for_same_seed`(`assert_frame_equal`)。审查 grep 确认全文件仅入口与 `include_fuzzy_sample` 单次抽样两处重置,无行级 loop 内重置。
