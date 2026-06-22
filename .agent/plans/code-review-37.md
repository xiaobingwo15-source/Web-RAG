# Code Review — PR #37

## Critical Findings (fix before next deploy)

### 1. Frontend polling dead code (useChat.ts:130) — CONFIRMED
`lastMsg?.role === 'user'` can never be true because `save_message_streaming()` inserts an assistant placeholder BEFORE the pipeline starts. Polling never triggers.

**Fix**: Change condition to `lastMsg?.role === 'assistant' && !lastMsg?.content && lastMsg?.id` — detect the empty placeholder.

### 2. Pipeline exceptions produce 'done' instead of 'error' (chat.py:270) — CONFIRMED
`_run_pipeline` catches Exception, saves error text, pushes sentinel. SSE generator yields 'done'. Live-streaming client sees success on failure.

**Fix**: Push an error event to the queue before returning from the except block, or have the SSE generator check the saved status.

### 3. CancelledError leaves orphan streaming messages (chat.py:283) — CONFIRMED
CancelledError (BaseException) bypasses except Exception. Placeholder stays status='streaming' forever.

**Fix**: Add `except BaseException` or use a try/finally that always calls update_message_content.

### 4. Widget assistant_msg_id can be None (widget.py:172) — CONFIRMED
If save_widget_message_streaming returns unexpected shape, all persistence silently skips.

**Fix**: Fail loudly — raise or yield an error event if assistant_msg_id is None.

## Moderate Findings

### 5. assistant_message SSE event not handled (useChat.ts / api.ts) — CONFIRMED
Backend emits it, frontend drops it. Harmless but the ID mapping is lost.

### 6. Unbounded queue with dead QueueFull handlers (chat.py:219) — CONFIRMED
Queue() has no maxsize. except QueueFull is dead code.

### 7. Widget forwards rag_quality events to client (widget.py:248) — CONFIRMED
chat.py filters them; widget.py uses catch-all yield.

### 8. ensure_future instead of create_task (chat.py:281) — CONFIRMED
Python 3.12+ deprecation warning. No exception callback on the task.

## Cleanup Findings (non-urgent)

### 9. _enforce_global_page_limit called twice (pdf_parser.py:66) — CONFIRMED
Redundant second call in extract_pdf after _inspect_pdf already checked.
