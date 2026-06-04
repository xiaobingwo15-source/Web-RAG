# Reduce Frontend Post-Click Latency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut perceived latency from chat-send to first visible token by pre-warming widget sessions, batching SSE token renders, and exposing real time-to-first-token metrics.

**Architecture:** Four independent changes to the frontend React layer — (1) eagerly resolve the anonymous widget session when the widget opens instead of on first send, (2) batch SSE token callbacks into `requestAnimationFrame` flushes so React reconciles once per frame instead of once per token, (3) replace the meaningless `markInteraction` timing with a real send-to-first-chunk timer, (4) thread `AbortController` through the stream layer so callers can cancel in-flight requests.

**Tech Stack:** React 18, TypeScript, Vite, Fetch API (SSE via ReadableStream), `performance.mark`/`performance.measure`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/hooks/useAnonymousChat.ts` | Modify | Pre-warm session on call, batch token updates, expose `cancel()` |
| `frontend/src/hooks/useChat.ts` | Modify | Batch token updates, expose `cancel()` |
| `frontend/src/lib/api.ts` | Modify | Return `AbortController` from `streamChat` / `streamWidgetChat` |
| `frontend/src/components/landing/ChatWidget.tsx` | Modify | Call `preWarmSession` on widget open |
| `frontend/src/lib/performance.ts` | Modify | Add `LatencyTimer` class for real send→first-token measurement |

---

### Task 1: Add `LatencyTimer` to `performance.ts`

**Files:**
- Modify: `frontend/src/lib/performance.ts`

- [ ] **Step 1: Write the `LatencyTimer` class**

Add this after the existing `markRouteReady` function in `frontend/src/lib/performance.ts`:

```typescript
/**
 * Measures wall-clock time from an interaction start to an arbitrary end marker.
 * Usage:
 *   const timer = new LatencyTimer('chat.send')
 *   // ... later, when first token arrives:
 *   timer.markFirstToken()
 *   // ... when stream ends:
 *   timer.markDone()
 */
export class LatencyTimer {
  private name: string
  private startTime: number
  private firstTokenMs: number | null = null
  private doneMs: number | null = null

  constructor(name: string) {
    this.name = name
    this.startTime = performance.now()
  }

  markFirstToken(): number {
    if (this.firstTokenMs !== null) return this.firstTokenMs
    this.firstTokenMs = Math.round(performance.now() - this.startTime)
    window.dispatchEvent(
      new CustomEvent('web-rag:latency', {
        detail: {
          name: this.name,
          phase: 'first_token',
          ms: this.firstTokenMs,
        },
      }),
    )
    return this.firstTokenMs
  }

  markDone(): number {
    if (this.doneMs !== null) return this.doneMs
    this.doneMs = Math.round(performance.now() - this.startTime)
    window.dispatchEvent(
      new CustomEvent('web-rag:latency', {
        detail: {
          name: this.name,
          phase: 'done',
          ms: this.doneMs,
          first_token_ms: this.firstTokenMs,
        },
      }),
    )
    return this.doneMs
  }

  get firstTokenLatency(): number | null {
    return this.firstTokenMs
  }

  get totalLatency(): number | null {
    return this.doneMs
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd d:/RAG/Web-RAG/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors from `performance.ts`

- [ ] **Step 3: Commit**

```bash
cd d:/RAG/Web-RAG
git add frontend/src/lib/performance.ts
git commit -m "feat: add LatencyTimer for real send-to-first-token measurement"
```

---

### Task 2: Return `AbortController` from stream functions in `api.ts`

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add return type and return the controller from `streamChat`**

In `frontend/src/lib/api.ts`, change the `streamChat` function signature and body.

Replace the function signature (line 20-34) with:

```typescript
export interface StreamHandle {
  abort: () => void
}

export async function streamChat(
  message: string,
  threadId: string | null,
  token: string,
  onChunk: (text: string) => void,
  onDone: (messageId?: string) => void,
  onError: (err: StreamError) => void,
  onThreadId?: (threadId: string) => void,
  useDocuments: boolean = false,
  retrievalMode: string = 'hybrid',
  images?: string[],
  onThought?: (thought: string, action?: ActionMeta) => void,
  onSources?: (sources: RetrievalSource[]) => void,
  replyTo?: string,
): Promise<StreamHandle> {
```

Then at the end of the function, after the `try/catch` block (around line 124), add:

```typescript
  return { abort: () => controller.abort() }
```

Also change the early-return error paths (lines 57-61 and 63-67) to return a no-op handle:

```typescript
    // In the catch block (line 57-61):
    return { abort: () => {} }

    // After the !response.ok check (line 63-67):
    return { abort: () => {} }

    // After the !reader check (line 72-75):
    return { abort: () => {} }
```

- [ ] **Step 2: Add return type and return the controller from `streamWidgetChat`**

Apply the same changes to `streamWidgetChat` (line 145-231). Change the signature to return `Promise<StreamHandle>` and add `return { abort: () => controller.abort() }` at the end, and `return { abort: () => {} }` at each early-return path.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd d:/RAG/Web-RAG/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd d:/RAG/Web-RAG
git add frontend/src/lib/api.ts
git commit -m "feat: return StreamHandle with abort() from stream functions"
```

---

### Task 3: Pre-warm anonymous widget session on widget open

**Files:**
- Modify: `frontend/src/hooks/useAnonymousChat.ts`
- Modify: `frontend/src/components/landing/ChatWidget.tsx`

- [ ] **Step 1: Add `preWarmSession` to `useAnonymousChat`**

In `frontend/src/hooks/useAnonymousChat.ts`, add `preWarmSession` to the returned object. The existing `ensureSession` already caches — we just need to expose it as a named action.

Replace the return statement (line 97) with:

```typescript
  const preWarmSession = useCallback(() => {
    // Fire and forget — populates sessionRef.current for the first sendMessage
    ensureSession()
  }, [ensureSession])

  return { messages, sendMessage, isStreaming, authError, limitReached, preWarmSession }
```

- [ ] **Step 2: Call `preWarmSession` when the widget opens**

In `frontend/src/components/landing/ChatWidget.tsx`, destructure `preWarmSession` from the hook and call it on open.

Change line 10:

```typescript
  const { messages, sendMessage, isStreaming, authError, limitReached, preWarmSession } = useAnonymousChat()
```

Change the open button's `onClick` (line 63-66):

```typescript
          onClick={() => {
            markInteraction('widget.open')
            setOpen(true)
            preWarmSession()
          }}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd d:/RAG/Web-RAG/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd d:/RAG/Web-RAG
git add frontend/src/hooks/useAnonymousChat.ts frontend/src/components/landing/ChatWidget.tsx
git commit -m "feat: pre-warm widget session on widget open instead of first send"
```

---

### Task 4: Batch SSE token updates with `requestAnimationFrame`

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/hooks/useAnonymousChat.ts`

- [ ] **Step 1: Add rAF-batched token flush to `useChat`**

In `frontend/src/hooks/useChat.ts`, add a ref-based token buffer that flushes on animation frames.

Add these imports at the top (replace line 1):

```typescript
import { useState, useCallback, useRef, useEffect } from 'react'
```

Add these refs inside the `useChat` function, after the existing refs (after line 25):

```typescript
  const tokenBuffer = useRef<string>('')
  const rafId = useRef<number | null>(null)
```

Add a flush helper after the refs:

```typescript
  const flushTokens = useCallback(() => {
    rafId.current = null
    const buffered = tokenBuffer.current
    if (!buffered) return
    tokenBuffer.current = ''
    setMessages((prev) => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      updated[updated.length - 1] = {
        ...last,
        content: last.content + buffered,
      }
      return updated
    })
  }, [])
```

Add cleanup in an effect (after the flush helper):

```typescript
  useEffect(() => {
    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    }
  }, [])
```

In `sendMessage`, replace the `onChunk` callback (lines 106-114) with:

```typescript
      (chunk) => {
        tokenBuffer.current += chunk
        if (rafId.current === null) {
          rafId.current = requestAnimationFrame(flushTokens)
        }
      },
```

Also flush any remaining tokens in the `onDone` callback (after line 117, before `setIsStreaming(false)`):

```typescript
      (messageId) => {
        // Flush any buffered tokens before marking done
        if (rafId.current !== null) {
          cancelAnimationFrame(rafId.current)
          rafId.current = null
        }
        const buffered = tokenBuffer.current
        tokenBuffer.current = ''
        setIsStreaming(false)
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (!last || last.role !== 'assistant') return updated
          let actions = last.actions
          if (actions && actions.length > 0 && currentActionRef.current) {
            actions = [...actions]
            actions[actions.length - 1] = { ...actions[actions.length - 1], status: "completed" }
          }
          updated[updated.length - 1] = {
            ...last,
            content: last.content + buffered,
            ...(messageId ? { id: messageId } : {}),
            actions,
          }
          return updated
        })
        currentActionRef.current = null
      },
```

- [ ] **Step 2: Add rAF-batched token flush to `useAnonymousChat`**

In `frontend/src/hooks/useAnonymousChat.ts`, apply the same pattern.

Add import (line 1):

```typescript
import { useState, useCallback, useRef, useEffect } from 'react'
```

Add refs and flush helper inside the hook (after `userMessageCount` ref, line 18):

```typescript
  const tokenBuffer = useRef('')
  const rafId = useRef<number | null>(null)

  const flushTokens = useCallback(() => {
    rafId.current = null
    const buffered = tokenBuffer.current
    if (!buffered) return
    tokenBuffer.current = ''
    setMessages((prev) => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      updated[updated.length - 1] = { ...last, content: last.content + buffered }
      return updated
    })
  }, [])

  useEffect(() => {
    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    }
  }, [])
```

In `sendMessage`, replace the `onChunk` callback (lines 50-59) with:

```typescript
        (chunk) => {
          tokenBuffer.current += chunk
          if (rafId.current === null) {
            rafId.current = requestAnimationFrame(flushTokens)
          }
        },
```

In the `onDone` callback (line 61), flush before clearing streaming:

```typescript
        () => {
          if (rafId.current !== null) {
            cancelAnimationFrame(rafId.current)
            rafId.current = null
          }
          const buffered = tokenBuffer.current
          tokenBuffer.current = ''
          if (buffered) {
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              updated[updated.length - 1] = { ...last, content: last.content + buffered }
              return updated
            })
          }
          setIsStreaming(false)
        },
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd d:/RAG/Web-RAG/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd d:/RAG/Web-RAG
git add frontend/src/hooks/useChat.ts frontend/src/hooks/useAnonymousChat.ts
git commit -m "perf: batch SSE token updates with requestAnimationFrame"
```

---

### Task 5: Wire `LatencyTimer` and `AbortController` into chat hooks

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/hooks/useAnonymousChat.ts`

- [ ] **Step 1: Add `LatencyTimer` and `cancel` to `useChat`**

In `frontend/src/hooks/useChat.ts`, add the import:

```typescript
import { LatencyTimer } from '@/lib/performance'
```

Add a ref for the timer and abort handle (after `rafId` ref):

```typescript
  const latencyTimer = useRef<LatencyTimer | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
```

In `sendMessage`, create the timer right before calling `streamChat`:

```typescript
    latencyTimer.current = new LatencyTimer('chat.send')
```

Pass a modified `onChunk` that marks first token. Replace the `onChunk` callback body with:

```typescript
      (chunk) => {
        if (latencyTimer.current && latencyTimer.current.firstTokenLatency === null) {
          latencyTimer.current.markFirstToken()
        }
        tokenBuffer.current += chunk
        if (rafId.current === null) {
          rafId.current = requestAnimationFrame(flushTokens)
        }
      },
```

In the `onDone` callback, after flushing tokens, add:

```typescript
        latencyTimer.current?.markDone()
        latencyTimer.current = null
        abortRef.current = null
```

Capture the `StreamHandle` return value:

```typescript
    const handle = await streamChat(
      // ... existing args ...
    )
    abortRef.current = handle.abort
```

Add a `cancel` function and return it:

```typescript
  const cancel = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    if (rafId.current !== null) {
      cancelAnimationFrame(rafId.current)
      rafId.current = null
    }
    tokenBuffer.current = ''
    setIsStreaming(false)
  }, [])
```

Update the return statement (line 225):

```typescript
  return { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread, currentAction, cancel }
```

- [ ] **Step 2: Add `LatencyTimer` and `cancel` to `useAnonymousChat`**

In `frontend/src/hooks/useAnonymousChat.ts`, add the import:

```typescript
import { LatencyTimer } from '@/lib/performance'
```

Add refs (after `rafId` ref):

```typescript
  const latencyTimer = useRef<LatencyTimer | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
```

In `sendMessage`, create the timer before `streamWidgetChat`:

```typescript
      latencyTimer.current = new LatencyTimer('widget.send')
```

In the `onChunk` callback, mark first token:

```typescript
        (chunk) => {
          if (latencyTimer.current && latencyTimer.current.firstTokenLatency === null) {
            latencyTimer.current.markFirstToken()
          }
          tokenBuffer.current += chunk
          if (rafId.current === null) {
            rafId.current = requestAnimationFrame(flushTokens)
          }
        },
```

In the `onDone` callback, mark done and clear refs:

```typescript
        () => {
          // ... existing flush logic ...
          latencyTimer.current?.markDone()
          latencyTimer.current = null
          abortRef.current = null
          setIsStreaming(false)
        },
```

Capture the handle:

```typescript
      const handle = await streamWidgetChat(
        // ... existing args ...
      )
      abortRef.current = handle?.abort ?? null
```

Add a `cancel` function:

```typescript
  const cancel = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    if (rafId.current !== null) {
      cancelAnimationFrame(rafId.current)
      rafId.current = null
    }
    tokenBuffer.current = ''
    setIsStreaming(false)
  }, [])
```

Update the return statement:

```typescript
  return { messages, sendMessage, isStreaming, authError, limitReached, preWarmSession, cancel }
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd d:/RAG/Web-RAG/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd d:/RAG/Web-RAG
git add frontend/src/hooks/useChat.ts frontend/src/hooks/useAnonymousChat.ts
git commit -m "feat: wire LatencyTimer and AbortController into chat hooks"
```

---

### Task 6: Verify end-to-end with manual smoke test

**Files:** None (manual verification)

- [ ] **Step 1: Start the dev server**

Run: `cd d:/RAG/Web-RAG/frontend && npm run dev`

- [ ] **Step 2: Open the landing page and verify widget pre-warm**

1. Open the landing page in a browser.
2. Open DevTools → Network tab.
3. Click the chat widget FAB (floating button).
4. **Verify:** You should see `resolveTenant` and `createWidgetSession` requests fire immediately on click, before typing anything.
5. Type a message and send.
6. **Verify:** The stream starts without the session-setup delay — the first token should arrive noticeably faster.

- [ ] **Step 3: Verify latency events in console**

1. In DevTools → Console, run:
   ```javascript
   window.addEventListener('web-rag:latency', e => console.log('LATENCY:', e.detail))
   ```
2. Send a message in the widget.
3. **Verify:** You see `{ name: 'widget.send', phase: 'first_token', ms: <number> }` and `{ name: 'widget.send', phase: 'done', ms: <number> }`.

- [ ] **Step 4: Verify token batching (no jank)**

1. Send a long question that produces a multi-sentence answer.
2. In React DevTools, observe the assistant message component.
3. **Verify:** The content updates in smooth chunks (once per animation frame) rather than character-by-character.

- [ ] **Step 5: Commit any fixes**

If any issues were found and fixed during smoke testing:

```bash
cd d:/RAG/Web-RAG
git add -A
git commit -m "fix: address issues found during latency smoke test"
```
