type Detail = Record<string, string | number | boolean | null | undefined>

export function markInteraction(name: string, detail: Detail = {}) {
  if (typeof window === 'undefined' || !window.performance) return
  const startedAt = performance.now()
  const startMark = `interaction:${name}:start:${startedAt}`
  performance.mark(startMark)

  requestAnimationFrame(() => {
    const duration = performance.now() - startedAt
    performance.measure(`interaction:${name}`, startMark)
    window.dispatchEvent(new CustomEvent('web-rag:interaction', {
      detail: { name, duration_ms: Math.round(duration), ...detail },
    }))
  })
}

export function markRouteReady(route: string) {
  if (typeof window === 'undefined' || !window.performance) return
  requestAnimationFrame(() => {
    performance.mark(`route:${route}:ready`)
    window.dispatchEvent(new CustomEvent('web-rag:route-ready', {
      detail: { route, ready_at_ms: Math.round(performance.now()) },
    }))
  })
}

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
