# ADR-34.1：当前应用模块边界

- 状态：accepted
- 日期：2026-07-20

## 背景

`services/reconciliation.py` 与 `services/workflow.py` 在连续功能迭代中同时承载应用编排、输入处理、并发、持久化、工具调用、审计决策和可观测性。行为测试能够防止回归，但无法阻止入口文件持续膨胀，导致当前系统难以阅读和定位。

## 决策

保持 API、数据库结构、状态枚举、事件顺序和失败语义不变，将已经稳定的职责拆分为以下模块：

- `reconciliation_input.py`：文件边界、任务哈希和匹配结果转换。
- `reconciliation_batch.py`：有界并发、准入控制、顺序归并和批次汇总。
- `reconciliation_flow.py`：单条 flow 的工作流调用和写入数据组装。
- `reconciliation_persistence.py`：核心事务与提交后的 best-effort 副作用。
- `reconciliation_types.py`：批次与 flow 之间的数据契约。
- `workflow_types.py`：工作流状态、分支常量和工具协议。
- `workflow_runtime.py`：Trace、SSE、token 和日志投影。
- `workflow_tools.py`：只读工具上下文、调用和失败语义。
- `workflow_decision.py`：审计调用、Schema、业务约束和决策路由。

`ReconciliationService` 和 `run_item` 继续作为兼容入口。入口文件只负责编排，不重新定义已经下沉的实现。

依赖方向固定为：

```text
API / Worker
  -> reconciliation.py
      -> input / batch / flow / persistence
          -> workflow.py
              -> workflow types / runtime / tools / decision
```

底层模块不得反向导入 API，也不得通过入口服务私有属性访问数据库或队列。

## 取舍

- 不在本次重组中修改业务规则、引入新的框架或重写状态模型。
- 保留少量兼容导出，避免 API、Worker 和既有测试同时迁移。
- 文件拆分以稳定职责为依据，不以追求固定行数为目标。
- 内部测试的 monkeypatch 路径随真实模块归属更新，但不减少断言或覆盖场景。

## 验收

- 现有定向测试与全量回归结果不变。
- Ruff 与 `git diff --check` 通过。
- README 链接到唯一的当前系统地图，并明确区分当前实现与规划能力。
