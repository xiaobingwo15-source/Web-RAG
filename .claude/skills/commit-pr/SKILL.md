---
name: commit-pr
description: Use when the user asks to commit, push, or create a PR. Handles conventional commits, push, PR creation, and merge conflict resolution for this project's Staging→master workflow.
---

# Commit & PR Workflow

## Overview

Commit staged changes, push to origin, and create a PR from Staging to master. Handles merge conflicts automatically.

**Announce at start:** "I'm using the commit-pr skill."

## Project Conventions

- **Branch flow:** `Staging` → `master` (always PR from Staging)
- **Remote:** `origin` = `xiaobingwo15-source/Web-RAG`
- **gh flag:** Always use `--repo xiaobingwo15-source/Web-RAG` for all `gh` commands
- **Commit format:** Conventional commits — `feat(area):`, `fix(area):`, `docs(area):`, `merge:`
- **PR body:** Use change summary table classified by category (frontend, backend, supabase, etc.)

## Steps

### 1. Check State & Verify

```bash
git status
git diff --stat
git log --oneline -3   # check recent commit style
```

**Before staging, verify each file's diff:**
```bash
git diff <file>   # review actual changes per file
```

- Confirm changes are intentional and correct
- Check for accidental deletions, debug code, or sensitive data
- If pre-existing unrelated changes exist (e.g., settings, workflows), note them in the commit or ask user
- Only proceed to staging after verification passes

If nothing is staged, ask user what to commit.

### 2. Commit

```bash
git commit -m "<type>(<area>): <description>

<bullet points of key changes>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Commit type prefixes:**
| Prefix | When |
|--------|------|
| `feat(area):` | New feature or enhancement |
| `fix(area):` | Bug fix |
| `docs(area):` | Documentation only |
| `merge:` | Merge conflict resolution |
| `refactor(area):` | Code restructuring, no behavior change |
| `chore(area):` | Config, deps, tooling |

**Area examples:** `rag`, `chat`, `auth`, `embeddings`, `database`, `frontend`, `backend`, `admin`, `config`

### 3. Push

```bash
git push origin <current-branch>
```

### 4. Create PR

```bash
gh pr create \
  --base master \
  --head <current-branch> \
  --title "<commit message title>" \
  --body "## Summary
- <bullet 1>
- <bullet 2>

## Changes

| Category | File | Change |
|----------|------|--------|
| Backend | file.py | What changed |
| Frontend | file.tsx | What changed |

## Notes
- <any caveats, migration notes, env var changes>

🤖 Generated with [Claude Code](https://claude.com/claude-code)" \
  --repo xiaobingwo15-source/Web-RAG
```

### 5. Handle Merge Conflicts (if any)

If `gh pr create` fails with "No commits between master and Staging" or merge conflicts:

```bash
# Fetch latest master
git fetch origin master

# Try merge to see conflicts
git merge origin/master --no-commit --no-ff 2>&1

# List conflicted files
git diff --name-only --diff-filter=U
```

For each conflicted file:
1. Read the file, find `<<<<<<<` / `=======` / `>>>>>>>` markers
2. Resolve by keeping the best of both sides (usually Staging's structure + master's new features)
3. Edit to remove conflict markers
4. `git add <file>`
5. `git commit -m "merge: resolve <file> conflict — <what was kept from each side>"`
6. `git push origin <branch>`
7. Retry `gh pr create`

### 6. Verify & Merge

```bash
# Check PR is mergeable
gh pr view <number> --repo xiaobingwo15-source/Web-RAG --json mergeable,mergeStateStatus

# If CLEAN, merge
gh pr merge <number> --merge --repo xiaobingwo15-source/Web-RAG
```

## Quick Reference

```
User says "commit and push" → stage, commit, push, create PR
User says "just commit" → stage, commit (no push)
User says "create PR" → push + create PR (skip commit if already committed)
Merge conflict → fetch master, merge, resolve, commit, push, retry PR
```

## Common Mistakes

**Forgetting `--repo` flag**
- `gh pr create` without `--repo xiaobingwo15-source/Web-RAG` fails because `gh` defaults to the `upstream` remote
- Always include `--repo xiaobingwo15-source/Web-RAG`

**Wrong base branch**
- Always PR to `master`, not `main`
- Always from `Staging` (or current branch), never from `master` directly

**Merge conflict on App.tsx**
- Common conflict: Staging uses lazy loading, master may have direct imports
- Resolution: keep lazy-loaded imports + Suspense, add any new features from master (like SpeedInsights)
