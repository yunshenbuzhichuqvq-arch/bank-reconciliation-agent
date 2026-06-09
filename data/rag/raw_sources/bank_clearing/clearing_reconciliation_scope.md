---
source_name: 支付结算对账口径说明（模拟摘录）
source_url: https://example.com/bank-clearing/reconciliation-scope
source_type: markdown
business_tags: amount_mismatch, clearing_file_exception, audit_trail
---

# 支付结算对账口径说明（模拟摘录）

## 清算对账字段口径

清算对账需要同时核验清算流水、核心入账流水、金额字段和业务参考号。出现文件缺失、金额不平或跨日补记时，应根据清算业务口径区分异常类型，不得沿用银企场景的客户侧解释。

本项目抽象规则：`BANK_CLEARING` 场景的 RAG 依据必须来自清算领域资料，避免把银企查询查复话术误用到清算跨日切异常。

## 自动结论边界

只有在金额、业务单号和记账日期证据闭环时，系统才能输出已配对或可自动平账建议。证据不完整时必须转人工，并在原因中说明缺失项。

本项目抽象规则：清算 RAG 无命中、或命中但不能支撑结论时，工作流仍需保持人工兜底，不允许编造规则来源。
