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
