---
source_name: 清算单边差错处置手册（模拟摘录）
source_url: https://example.com/bank-clearing/single-side
source_type: markdown
business_tags: single_side_missing, query_reply, clearing_operations
---

# 清算单边差错处置手册（模拟摘录）

## 非日切窗口单边核查

清算侧或核心侧只有一边存在流水，且不在日切窗口内时，应按普通清算单边差错处理，进入查询查复或人工复核流程，不得直接平账。

本项目抽象规则：`BC-R001` 需要输出缺失侧、现有侧金额、来源文件和建议动作，默认指向人工或查询查复。

## 证据留存要求

单边差错的复核记录应保留来源系统、交易流水号、参考号、金额、交易时间和处置结论，保证后续可以追溯。

本项目抽象规则：无论是否命中 RAG，单边差错都需要把规则依据和证据链一起写入审计结果或人工复核说明。
