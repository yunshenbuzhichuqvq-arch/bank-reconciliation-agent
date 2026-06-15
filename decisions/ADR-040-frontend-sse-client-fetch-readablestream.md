# ADR-040: 前端 SSE 客户端——fetch + ReadableStream

- Status: Accepted (2026-06-15)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: frontend/src/api/stream.ts, frontend/src/composables/useReconcileStream.ts(ADR-041), frontend/src/types/api.ts(ADR-042), decisions/ADR-036(后端 SSE 端点), decisions/ADR-037(事件契约)

## Context

V1-1 的 SSE 端点 `POST /reconcile/stream` 是 multipart(`bank_file` + `clear_file` + `scenario_type`,鉴权 `X-User-ID`),返回 `text/event-stream`(帧 `data: {AgentStreamEvent JSON}\n\n`)。前端要消费它实时渲染。现有 `api/client.ts` 是 axios,response 拦截器解包 `.data.data`,不能处理流式响应。

## Options

- **A. 浏览器原生 `EventSource`** — Pros: 自动重连、API 极简。Cons: 只支持 GET、无法带自定义请求头与 body → 不能 POST multipart + `X-User-ID`,与端点契约根本不兼容(致命)。
- **B. `fetch` + `ReadableStream` 手动解析 SSE 帧(采纳)** — fetch POST(FormData + headers)→ `response.body.getReader()` → `TextDecoder` 累积 buffer → 按 `\n\n` 切帧 → 剥 `data:` 前缀 → `JSON.parse`。Pros: 契合 POST/multipart/自定义头;`AbortController` 可取消;无新依赖。Cons: 手写帧解析(半包/粘包跨 chunk);无自动重连;要处理流中断/HTTP 错误。
- **C. 引第三方库(如 `@microsoft/fetch-event-source`)** — Pros: 现成帧解析 + 重连。Cons: 新前端依赖;本 demo 帧解析不复杂,YAGNI。

## Decision

采用 **B**。`fetch` + `ReadableStream`,封装为 composable(ADR-041),手写 `\n\n` 帧解析(含半包 buffer),`AbortController` 取消;复用 `getDefaultHeaders()` 注入 `X-User-ID`。不引库、不用 `EventSource`。重连本 demo 不做(单次任务流,`task_done` 即结束)。

## Consequences

- 正面:契合 POST multipart 端点、复用鉴权头、零新依赖、可取消。
- 负面:手写帧解析须覆盖半包/粘包;无自动重连(流中断需用户重发);依赖 fetch streaming(现代浏览器 OK)。

## Implementation Note (V1-2 收尾)

落地 `api/stream.ts`:`streamReconcile(params, handlers, signal)` → fetch POST `/api/v1/reconcile/stream`(FormData + `getDefaultHeaders()`)→ `getReader()` + `TextDecoder({stream:true})` + buffer;`consumeFrames` 按 `\n\n` 切帧、`parseFrame` 取 `data:` 行 `JSON.parse`,校验 `schema_version`,`task_done` 触发 `onDone`;AbortError 静默 return;`finally reader.releaseLock()`。`stream.spec.ts` 覆盖单帧拆两 chunk / 两帧一 chunk / 非 2xx onError / abort 停止 / FormData+X-User-ID。残留技术债:流 `done` 后未 flush `TextDecoder`、未处理无 `\n\n` 结尾的残余 buffer——依赖后端"每帧 `\n\n` 结尾"契约保证(实际安全)。
