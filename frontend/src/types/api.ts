export interface Page<T>{ items:T[]; total:number; page:number; page_size:number }
export interface UploadResult{ task_id:string; status:string; total_bank_rows:number; total_clear_rows:number; auto_fixed_rows:number; pending_ai_rows:number; pending_human_rows:number }
export interface TaskStatus{ task_id:string; status:string; auto_fixed_rows:number; pending_ai_rows:number; ai_processed_rows:number; pending_human_rows:number; unresolved_rows:number }
export interface RagEvidence{ chunk_id:string; source:string; source_name:string; source_url:string; source_file:string; section_title:string; element_type:string; business_tags:string[]; score:number; content:string }
export interface AuditDecision{ flow_id:string; decision:string; risk_level:string; reason:string; evidence:RagEvidence[]; confidence:number }
export interface ExceptionItem{ flow_id:string; status:string; error_type:string; exception_branch:string|null; bank_amount:string|null; clear_amount:string|null; amount_diff:string|null; rag_evidence:RagEvidence[]; audit_decision:AuditDecision }
export interface ExceptionList{ task_id:string; total:number; items:ExceptionItem[] }
export interface RagSourceRef{ source:string; score:number|null }
export interface PendingReviewItem{ queue_id:number; error_type:string; exception_branch:string|null; risk_level:string; ai_suggestion:string; ai_confidence:number|null; ai_reason:string|null; rag_sources:RagSourceRef[]; similar_historical_cases:number; historical_approve_rate:string }
export interface PendingReviewList{ scenario_type:string; items:PendingReviewItem[]; total:number }
export type ReviewAction = "APPROVED_MATCH" | "FORCE_HOLD"
export interface ReviewResult{ queue_id:number; current_status:string; memory_updated:Record<string,boolean> }
export interface LedgerRow{ id:number; task_id:string; flow_id:string; error_type:string; exception_branch:string|null; bank_amount:string|null; clear_amount:string|null; discrepancy_amount:string; ai_audit_opinion:string|null; ai_confidence:string|null; rag_source:string|null; handle_status:string }

// Keep aligned with backend schemas/stream.py and services/stream_emitter.py.
export type StreamEventType = "task_started" | "hook" | "rag_retrieved" | "agent_decision" | "fallback" | "item_done" | "task_done"
export interface TaskStartedPayload{ scenario_type:string; total_rows?:number }
export interface HookPayload{ hook_name?:string; agent_name?:string; status?:string; step?:string; [key:string]:unknown }
export interface RagRetrievedPayload{ agent_name?:string; chunk_ids:string[]; best_score:number; query:string; evidence?:RagEvidence[] }
export interface AgentDecisionPayload{ agent_name?:string; decision?:string; confidence?:number; evidence?:RagEvidence[]; next_action?:string; prompt_version?:string; reason?:string; fallback_level?:number; [key:string]:unknown }
export interface FallbackPayload{ agent_name?:string; fallback_level:number; reason?:string; next_action?:string; [key:string]:unknown }
export interface ItemDonePayload{ flow_id?:string; status:string; decision?:string; confidence?:number; [key:string]:unknown }
export interface TaskDonePayload{ status:string; total_bank_rows?:number; total_clear_rows?:number; auto_fixed_rows?:number; pending_ai_rows?:number; pending_human_rows?:number; ai_processed_rows?:number; fallback_l2_rows?:number; fallback_l3_rows?:number; error_message?:string }
export type StreamPayload = TaskStartedPayload | HookPayload | RagRetrievedPayload | AgentDecisionPayload | FallbackPayload | ItemDonePayload | TaskDonePayload
export interface AgentStreamEvent{ schema_version:string; event_type:StreamEventType; seq:number; task_id:string; flow_id:string|null; ts:string; payload:StreamPayload }
