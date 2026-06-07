import { apiGet, apiPost } from "./client";
import type { PendingReviewList, ReviewAction, ReviewResult } from "../types/api";

export function listPending(p:{task_id?:string;page?:number;page_size?:number}):Promise<PendingReviewList> {
  return apiGet<PendingReviewList>("/review/pending", p);
}

export function approveReview(
  queueId:number,
  body:{action:ReviewAction;handler_username:string;remark?:string},
):Promise<ReviewResult> {
  return apiPost<ReviewResult>(`/review/${queueId}/approve`, body);
}
