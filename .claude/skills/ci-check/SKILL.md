# CI Failure Triage

Quick diagnosis of GitHub Actions CI failures. Determines if it's a code issue or infrastructure problem.

**Trigger:** User says "CI failed", "checks failed", "why are CI checks failing", or CI checks show red after a push/PR.

## Steps

### 1. Get the failure summary
```bash
gh pr checks <number> --repo xiaobingwo15-source/Web-RAG
```

### 2. Check the run annotation (catches billing/infra issues instantly)
```bash
gh run view <run-id> --repo xiaobingwo15-source/Web-RAG
```
Look for annotations like:
- "account is locked due to billing issue" → **Not a code problem.** Tell user to fix billing at https://github.com/settings/billing
- "The job was not started" → Infrastructure issue, not code
- Resource limits, quota exceeded → GitHub-side issue

### 3. If it's a real test failure, get the logs
```bash
gh run view <run-id> --log-failed --repo xiaobingwo15-source/Web-RAG
```

### 4. Diagnose and fix
- **Billing/account lock** → User must resolve at github.com/settings/billing. Code is fine, can merge manually.
- **Test failure** → Read the failed test output, identify the failing test, fix the code, re-run locally, then push fix.
- **Build failure** → Check for TypeScript errors, missing imports, dependency issues.
- **Timeout** → Usually transient. Suggest rerun: `gh run rerun <run-id> --repo xiaobingwo15-source/Web-RAG`

### 5. Rerun after fix
```bash
gh run rerun <run-id> --repo xiaobingwo15-source/Web-RAG
```

## Quick Reference

| Symptom | Diagnosis | Action |
|---------|-----------|--------|
| "account is locked" | Billing issue | Fix at github.com/settings/billing |
| "job was not started" | Infra/quota | Retry or wait |
| pytest FAIL | Code bug | Fix code, push, rerun |
| TypeScript error | Build issue | Fix imports/types |
| Timeout | Transient | Rerun |
| All checks fail in <5s | Account-level issue | Not code related |
