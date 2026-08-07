# Generate Changelog

Generate a changelog from git commits between Staging and master.

**Trigger:** User says "generate changelog", "update changelog", "what changed since last release".

## Steps

### 1. Get commits since last merge to master
```bash
git log origin/master..origin/Staging --oneline --no-merges
```

If no commits on Staging, compare recent master commits:
```bash
git log --oneline -20 --no-merges
```

### 2. Categorize commits

Group by conventional commit prefix:
- `feat` → ✨ Features
- `fix` → 🐛 Bug Fixes
- `refactor` → ♻️ Refactors
- `docs` → 📝 Documentation
- `test` → ✅ Tests
- `chore` → 🔧 Chores

### 3. Generate CHANGELOG.md

Structure:
```markdown
# Changelog

## [Unreleased] — YYYY-MM-DD

### ✨ Features
| Commit | Date | Description |
|--------|------|-------------|
| abc1234 | 2026-07-27 | feat(rag): description here |

### 🐛 Bug Fixes
| Commit | Date | Description |
|--------|------|-------------|
```

### 4. Rules
- **No author names** — user preference (never include)
- Use commit date, not current date
- Link commits to PRs if visible in log
- Keep descriptions concise (from commit message)
- If CHANGELOG.md exists, prepend new entries at top

### 5. Update CLAUDE.md if migration reference changed
Check if any new migrations were added and update the "Latest migration" reference.
