import { apiGet } from "./client";
import type { LedgerRow, Page } from "../types/api";

export function listLedger(q:Partial<{
  task_id:string;
  error_type:string;
  handle_status:string;
  start_date:string;
  end_date:string;
  page:number;
  page_size:number;
}>):Promise<Page<LedgerRow>> {
  return apiGet<Page<LedgerRow>>("/ledger", q);
}
