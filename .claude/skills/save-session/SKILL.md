---
name: save-session
description: Use when the user asks to save session progress, snapshot the conversation, or update memory. Creates structured memory files so new sessions can pick up where this one left off.
---

# Save Session Progress

## Overview

Save the current session's work to persistent memory files. New sessions read these via the MEMORY.md index to understand project state without re-exploring.

**Announce at start:** "I'm using the save-session skill."

## Memory Location

All memory files: `C:\Users\User\.claude\projects\D--RAG-Web-RAG\memory\`

## Steps

### 1. Identify What to Save

Scan the conversation for:
- **Features implemented** — new code, config changes, migrations
- **Bugs fixed** — root cause, fix applied, files changed
- **Decisions made** — why one approach over another
- **Current blockers** — what's pending, what needs user input
- **Files changed** — list with what changed in each

### 2. Check for Existing Memory

Before creating new files, check if an existing memory file covers the same topic:

```bash
# Read the index
cat MEMORY.md

# Grep for related topics
grep -l "keyword" memory/*.md
```

If an existing file covers the same topic, **update it** instead of creating a duplicate.

### 3. Create/Update Memory File

**Naming:** `project_<topic>.md` for project state, `session_YYYY_MM_DD_<topic>.md` for session snapshots

**Template:**
```markdown
---
name: <short-kebab-case-slug>
description: <one-line summary>
metadata:
  type: project | feedback | user | reference
---

## What Changed
- <bullet points>

## Files Changed
| File | Change |
|------|--------|
| path/file.py | What changed |

## Key Decisions
- <decision> — <why>

## Current State
- <what's done>
- <what's pending>

**Why:** <why this was done>
**How to apply:** <what future sessions should know>
```

### 4. Update MEMORY.md Index

Add a one-line entry to `MEMORY.md`:
```markdown
- [Title](file.md) — hook description
```

### 5. Fix Stale Entries

If you notice outdated information in existing memory files (e.g., items listed as "not started" that are actually done), update them.

## Memory Types

| Type | Prefix | When |
|------|--------|------|
| `project` | `project_` | Features, fixes, architecture state |
| `feedback` | `feedback_` | User corrections, conventions |
| `user` | — | Who the user is, preferences |
| `reference` | — | External URLs, docs, dashboards |
| `session` | `session_` | Full session snapshot (when user says "save everything") |

## Rules

- **Never duplicate** — check existing files first
- **Update stale entries** — if memory says "not started" but it's done, fix it
- **Link related memories** — use `[[name]]` syntax in the body
- **Convert relative dates** — "today" → "2026-06-03"
- **Include Why/How to apply** — future sessions need context, not just facts
