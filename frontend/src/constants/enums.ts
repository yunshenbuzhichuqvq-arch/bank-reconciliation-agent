import type { ReviewAction } from "../types/api";

export type Tone = "success"|"warning"|"danger"|"info"|"neutral"
export const STATUS_META:Record<string,{label:string;tone:Tone}> = {
  UPLOADED:{label:"已上传",tone:"neutral"}, AI_RUNNING:{label:"AI 审计中",tone:"info"},
  AUTO_FIXED:{label:"自动平账",tone:"success"}, PENDING_HUMAN:{label:"待复核",tone:"warning"},
  FIXED:{label:"已平账",tone:"success"}, HELD:{label:"已挂账",tone:"danger"},
}
export const RISK_META:Record<string,{label:string;tone:Tone}> = {
  LOW:{label:"低",tone:"success"}, MEDIUM:{label:"中",tone:"warning"}, HIGH:{label:"高",tone:"danger"},
}
export const ERROR_TYPE_LABEL:Record<string,string> = {
  AMOUNT_MISMATCH:"金额不一致", NARRATIVE_NAME_MISMATCH:"摘要/户名不一致",
  BANK_UNARRIVED:"银行未到账", BOOK_UNRECORDED:"企业未入账", DUPLICATE_BOOKING:"疑似重复记账",
}
export const ACTION_LABEL:Record<ReviewAction,string> = { APPROVED_MATCH:"确认平账", FORCE_HOLD:"强制挂账" }
