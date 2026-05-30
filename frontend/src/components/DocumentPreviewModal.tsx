import { useState, useEffect, type ReactNode } from 'react'
import { X, FileText, Loader2, Copy, Check, Maximize2, Minimize2 } from 'lucide-react'
import { fetchDocumentChunks, type DocumentChunksResponse } from '@/lib/api'

/** Escape HTML special chars. */
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * Detect if a block of lines looks like a pipe-delimited table.
 * Requires at least 2 rows and 2 columns, with consistent pipe counts.
 */
function isPipeTable(lines: string[]): boolean {
  if (lines.length < 2) return false
  const pipeCounts = lines.map((l) => (l.match(/\|/g) || []).length)
  // Every row must have at least 2 pipes (i.e. 3+ columns)
  if (pipeCounts.some((c) => c < 2)) return false
  // A separator row like |---|---| is optional but common — filter it out for consistency
  const dataLines = lines.filter((l) => !/^\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$/.test(l))
  if (dataLines.length < 2) return false
  // All data rows should have similar pipe count (±1 tolerance)
  const counts = dataLines.map((l) => (l.match(/\|/g) || []).length)
  const max = Math.max(...counts)
  const min = Math.min(...counts)
  return max - min <= 1
}

/** Parse pipe-delimited lines into an HTML table. */
function renderPipeTable(lines: string[]): string {
  // Filter out separator row (|---|---|)
  const dataLines = lines.filter((l) => !/^\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$/.test(l))
  if (dataLines.length === 0) return ''

  const parseCells = (line: string): string[] => {
    // Strip leading/trailing pipe, then split
    const stripped = line.replace(/^\|/, '').replace(/\|$/, '')
    return stripped.split('|').map((c) => c.trim())
  }

  const rows = dataLines.map(parseCells)
  const colCount = Math.max(...rows.map((r) => r.length))

  // First row is header
  const header = rows[0]
  const body = rows.slice(1)

  let html = '<div class="table-scroll"><table><thead><tr>'
  for (let i = 0; i < colCount; i++) {
    html += `<th>${esc(header[i] || '')}</th>`
  }
  html += '</tr></thead><tbody>'
  for (const row of body) {
    html += '<tr>'
    for (let i = 0; i < colCount; i++) {
      html += `<td>${esc(row[i] || '')}</td>`
    }
    html += '</tr>'
  }
  html += '</tbody></table></div>'
  return html
}

/**
 * Convert plain text into rich-text HTML.
 * - Detects pipe-delimited tables and renders them as <table>
 * - Double newlines → paragraphs
 * - Single newlines → <br>
 */
function textToRichHtml(text: string): string {
  const blocks = text.split(/\n{2,}/)
  const parts: string[] = []

  for (const block of blocks) {
    const trimmed = block.trim()
    if (!trimmed) continue

    const lines = trimmed.split('\n')

    // Check if this block is a pipe-delimited table
    if (isPipeTable(lines)) {
      parts.push(renderPipeTable(lines))
      continue
    }

    // Regular paragraph — preserve single newlines as <br>
    const withBreaks = trimmed.replace(/\n/g, '<br>')
    parts.push(`<p>${withBreaks}</p>`)
  }

  return parts.join('')
}

function splitWhitespaceCells(line: string): string[] {
  return line.trim().split(/\s{2,}|\t+/).map((cell) => cell.trim()).filter(Boolean)
}

function isWhitespaceTable(lines: string[]): boolean {
  if (lines.length < 3) return false
  const rows = lines.map(splitWhitespaceCells)
  if (rows.some((row) => row.length < 2)) return false

  const columnCounts = rows.map((row) => row.length)
  const max = Math.max(...columnCounts)
  const min = Math.min(...columnCounts)

  const hasStableColumns = max >= 2 && max - min <= 1
  const hasEnoughStructure = max >= 3 || rows.slice(1).every((row) => row.length === rows[0].length)

  return hasStableColumns && hasEnoughStructure
}

function renderWhitespaceTable(lines: string[]): string {
  const rows = lines.map(splitWhitespaceCells)
  const colCount = Math.max(...rows.map((row) => row.length))
  const [header = [], ...body] = rows

  let html = '<div class="table-scroll"><table><thead><tr>'
  for (let i = 0; i < colCount; i++) {
    html += `<th>${esc(header[i] || '')}</th>`
  }
  html += '</tr></thead><tbody>'

  for (const row of body) {
    html += '<tr>'
    for (let i = 0; i < colCount; i++) {
      html += `<td>${esc(row[i] || '')}</td>`
    }
    html += '</tr>'
  }

  html += '</tbody></table></div>'
  return html
}

function inlineMarkdown(text: string): string {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
}

function startsLikeContinuation(line: string): boolean {
  return /^[a-z(]/.test(line.trim())
}

function endsLikeContinuation(line: string): boolean {
  return /(?:,|;|:|\b(?:and|or|while|with|for|to|of|in|the|a|an))$/i.test(line.trim())
}

function shouldJoinTextLines(previous: string, next: string): boolean {
  return startsLikeContinuation(next) || endsLikeContinuation(previous)
}

function looksImportantStandaloneLine(line: string): boolean {
  const trimmed = line.trim().replace(/:$/, '')
  if (!trimmed || trimmed.length > 90 || /[.!?]$/.test(trimmed)) return false

  const lower = trimmed.toLowerCase()
  if (
    [
      'available colors',
      'colors',
      'features',
      'signature features',
      'key features',
      'specifications',
      'product specifications',
      'description',
      'model',
      'keywords',
      'summary',
    ].includes(lower)
  ) {
    return true
  }

  if (/^[A-Z]{2,}\d[A-Z0-9-]{2,}$/.test(trimmed)) return true
  if (/^[A-Z][A-Za-z0-9/&+,\- ™®]{2,}$/.test(trimmed)) {
    return trimmed.split(/\s+/).length <= 8
  }

  return false
}

function renderReflowedTextLines(lines: string[]): string {
  const paragraphs: string[] = []
  let current = ''

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) continue

    if (!current) {
      current = line
      continue
    }

    if (shouldJoinTextLines(current, line)) {
      current = `${current} ${line}`
    } else {
      paragraphs.push(current)
      current = line
    }
  }

  if (current) paragraphs.push(current)

  return paragraphs
    .map((paragraph) => {
      const className = looksImportantStandaloneLine(paragraph) ? 'doc-text-line doc-key-line' : 'doc-text-line'
      const content = looksImportantStandaloneLine(paragraph)
        ? `<strong>${inlineMarkdown(paragraph)}</strong>`
        : inlineMarkdown(paragraph)
      return `<p class="${className}">${content}</p>`
    })
    .join('')
}

function textToDocumentHtml(text: string): string {
  if (!text.trim()) return textToRichHtml(text)

  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const parts: string[] = []
  let i = 0

  const collectTableLines = (
    start: number,
    predicate: (line: string) => boolean,
  ): { block: string[]; next: number } => {
    const block: string[] = []
    let cursor = start

    while (cursor < lines.length) {
      const line = lines[cursor]
      if (!line.trim() || !predicate(line)) break
      block.push(line)
      cursor += 1
    }

    return { block, next: cursor }
  }

  while (i < lines.length) {
    const trimmed = lines[i].trim()
    if (!trimmed) {
      i += 1
      continue
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      const depth = Math.min((trimmed.match(/^#+/)?.[0].length || 2), 3)
      const content = trimmed.replace(/^#{1,6}\s+/, '')
      parts.push(`<h${depth}>${inlineMarkdown(content)}</h${depth}>`)
      i += 1
      continue
    }

    if (/^---+$/.test(trimmed)) {
      parts.push('<hr>')
      i += 1
      continue
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(`<li>${inlineMarkdown(lines[i].trim().replace(/^[-*]\s+/, ''))}</li>`)
        i += 1
      }
      parts.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    if (trimmed.includes('|')) {
      const { block, next } = collectTableLines(i, (line) => line.trim().includes('|'))
      if (isPipeTable(block)) {
        parts.push(renderPipeTable(block))
        i = next
        continue
      }
    }

    if (splitWhitespaceCells(trimmed).length >= 2) {
      const { block, next } = collectTableLines(i, (line) => splitWhitespaceCells(line).length >= 2)
      if (isWhitespaceTable(block)) {
        parts.push(renderWhitespaceTable(block))
        i = next
        continue
      }
    }

    const paragraphLines: string[] = []
    while (i < lines.length) {
      const line = lines[i]
      const current = line.trim()
      if (!current) break
      if (
        paragraphLines.length > 0
        && (/^#{1,6}\s+/.test(current)
          || /^[-*]\s+/.test(current)
          || /^---+$/.test(current)
          || current.includes('|'))
      ) {
        break
      }
      paragraphLines.push(line)
      i += 1
    }

    if (paragraphLines.length > 0) {
      parts.push(renderReflowedTextLines(paragraphLines))
      continue
    }

    parts.push(`<p>${inlineMarkdown(trimmed)}</p>`)
    i += 1
  }

  return parts.join('')
}

export function DocumentPreviewModal({
  documentId,
  token,
  onClose,
}: {
  documentId: string
  token: string
  onClose: () => void
}) {
  const [data, setData] = useState<DocumentChunksResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [contentFullscreen, setContentFullscreen] = useState(false)

  useEffect(() => {
    let cancelled = false

    Promise.resolve()
      .then(() => {
        if (cancelled) return null
        setLoading(true)
        setError(null)
        return fetchDocumentChunks(documentId, token)
      })
      .then((res) => {
        if (!cancelled && res) setData(res)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Failed to load document')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [documentId, token])

  useEffect(() => {
    if (!contentFullscreen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setContentFullscreen(false)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [contentFullscreen])

  const handleCopy = async () => {
    if (!data?.full_text) return
    await navigator.clipboard.writeText(data.full_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const renderContentToolbar = (): ReactNode => (
    <div className="mb-2 flex items-center justify-between gap-3 shrink-0">
      <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Document Content
      </h3>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setContentFullscreen((f) => !f)}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          title={contentFullscreen ? 'Exit content fullscreen' : 'Fullscreen content'}
        >
          {contentFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          <span>{contentFullscreen ? 'Exit' : 'Fullscreen'}</span>
        </button>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-green-500" />
              <span className="text-green-500">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy all</span>
            </>
          )}
        </button>
      </div>
    </div>
  )

  const renderDocumentContent = (): ReactNode => (
    <div
      className={`${contentFullscreen ? 'flex-1 min-h-0' : 'max-h-[50vh]'} overflow-y-auto rounded-lg border border-border bg-white px-6 py-8 sm:px-8 text-slate-700 shadow-sm doc-content`}
    >
      <div
        className="doc-rich-text max-w-none"
        dangerouslySetInnerHTML={{ __html: textToDocumentHtml(data?.full_text || '') }}
      />
    </div>
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <style>{`
        .doc-content {
          scroll-behavior: smooth;
          scrollbar-gutter: stable;
        }
        .doc-content-fullscreen {
          animation: docContentFullscreenIn 180ms ease-out;
        }
        @keyframes docContentFullscreenIn {
          from {
            opacity: 0.94;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        /* === Blog-style article typography === */
        .doc-rich-text {
          color: #1e293b;
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          font-size: 1.0625rem;
          line-height: 1.8;
          letter-spacing: -0.006em;
          width: 100%;
          overflow-wrap: anywhere;
          word-break: normal;
          max-width: 72ch;
          margin: 0 auto;
        }

        /* Headings — clear hierarchy with breathing room */
        .doc-rich-text h1,
        .doc-rich-text h2,
        .doc-rich-text h3 {
          color: #0f172a;
          font-weight: 800;
          letter-spacing: -0.025em;
          line-height: 1.3;
        }
        .doc-rich-text h1 {
          font-size: 1.875rem;
          margin: 2.5rem 0 1rem;
          padding-bottom: 0.625rem;
          border-bottom: 2px solid #e2e8f0;
        }
        .doc-rich-text h2 {
          font-size: 1.5rem;
          margin: 2.25rem 0 0.875rem;
          padding-bottom: 0.5rem;
          border-bottom: 1px solid #e2e8f0;
        }
        .doc-rich-text h3 {
          font-size: 1.25rem;
          margin: 1.75rem 0 0.75rem;
          color: #334155;
        }
        .doc-rich-text h1:first-child,
        .doc-rich-text h2:first-child,
        .doc-rich-text h3:first-child {
          margin-top: 0;
        }

        /* Paragraphs — generous spacing for readability */
        .doc-rich-text p {
          margin: 0 0 1.5rem;
          width: 100%;
          max-width: none;
          white-space: normal;
        }
        .doc-rich-text p:last-child {
          margin-bottom: 0;
        }

        /* Reflowed text lines from document parsing */
        .doc-rich-text .doc-text-line {
          display: block;
          margin: 0 0 0.5rem;
          max-width: none;
          line-height: 1.8;
        }
        .doc-rich-text .doc-key-line {
          color: #0f172a;
          font-weight: 700;
          font-size: 1.0625rem;
          margin-top: 1.25rem;
          margin-bottom: 0.375rem;
        }

        /* Inline formatting */
        .doc-rich-text strong {
          color: #0f172a;
          font-weight: 700;
        }

        /* Lists — clean bullets with good indentation */
        .doc-rich-text ul {
          margin: 1rem 0 1.5rem;
          padding-left: 1.75rem;
          list-style: none;
        }
        .doc-rich-text ul li {
          position: relative;
          margin: 0.5rem 0;
          padding-left: 0.25rem;
          line-height: 1.75;
        }
        .doc-rich-text ul li::before {
          content: '';
          position: absolute;
          left: -1.25rem;
          top: 0.7em;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #94a3b8;
        }

        /* Horizontal rule — subtle section divider */
        .doc-rich-text hr {
          border: 0;
          height: 1px;
          background: linear-gradient(to right, transparent, #cbd5e1, transparent);
          margin: 2.5rem 0;
        }

        /* Tables — clean, modern, with rounded corners */
        .doc-content .table-scroll {
          overflow-x: auto;
          margin: 1.75rem 0 2rem;
          border: 1px solid #e2e8f0;
          border-radius: 10px;
          background: #ffffff;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }
        .doc-content table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.9375rem;
          line-height: 1.6;
        }
        .doc-content thead {
          background: #f8fafc;
        }
        .doc-content th {
          padding: 0.875rem 1.125rem;
          text-align: left;
          font-weight: 700;
          color: #0f172a;
          font-size: 0.8125rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          border-bottom: 2px solid #e2e8f0;
          white-space: normal;
        }
        .doc-content th:last-child,
        .doc-content td:last-child {
          border-right: 0;
        }
        .doc-content td {
          padding: 0.875rem 1.125rem;
          border-bottom: 1px solid #f1f5f9;
          color: #334155;
          vertical-align: top;
        }
        .doc-content tbody tr:last-child td {
          border-bottom: none;
        }
        .doc-content tbody tr:hover {
          background: #f8fafc;
        }
        .doc-content tbody tr:hover td {
          color: #0f172a;
        }

        /* Fullscreen article mode — wider, centered reading */
        .doc-content-fullscreen .doc-rich-text {
          max-width: 78ch;
          font-size: 1.125rem;
          line-height: 1.85;
        }
        .doc-content-fullscreen .doc-content {
          background: #fafbfc;
        }
      `}</style>
      <div
        className="relative mx-4 flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-background shadow-2xl transition-all duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3 min-w-0">
            <FileText className="h-5 w-5 shrink-0 text-primary" />
            <div className="min-w-0">
              <h2 className="truncate text-lg font-semibold text-foreground">
                {data?.metadata?.title || data?.filename || 'Loading...'}
              </h2>
              {data?.filename && data.metadata?.title && data.metadata.title !== data.filename && (
                <p className="truncate text-xs text-muted-foreground">{data.filename}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onClose}
              className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 min-h-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Loading document content...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <X className="h-8 w-8 text-red-500" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
          ) : data ? (
            <div className="space-y-4">
              {/* Metadata section */}
              {data.metadata?.summary && (
                <div className="rounded-lg border border-border bg-muted/30 p-4 shrink-0">
                  <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Summary
                  </h3>
                  <p className="text-sm leading-relaxed text-foreground">{data.metadata.summary}</p>
                </div>
              )}

              {/* Tags */}
              {data.metadata?.tags && data.metadata.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 shrink-0">
                  {data.metadata.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                  {data.metadata?.language && (
                    <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs text-primary">
                      {data.metadata.language}
                    </span>
                  )}
                  <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
                    {data.chunk_count} chunks
                  </span>
                </div>
              )}

              {/* Full text */}
              <div className="transition-all duration-300 ease-out">
                {contentFullscreen ? (
                  <div className="doc-content-fullscreen fixed inset-0 z-[60] flex flex-col bg-[#f8f9fb] p-4 sm:p-8">
                    <div className="mx-auto w-full max-w-4xl flex flex-col flex-1 min-h-0">
                      {renderContentToolbar()}
                      {renderDocumentContent()}
                    </div>
                  </div>
                ) : (
                  <>
                    {renderContentToolbar()}
                    {renderDocumentContent()}
                  </>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
