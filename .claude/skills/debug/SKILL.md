---
name: debug
description: Systematic debugging workflow for bugs, errors, and unexpected behavior. Use when the user reports a bug, error, crash, or unexpected behavior.
argument-hint: "[description-of-issue]"
allowed-tools: Bash Read Grep Glob Agent Edit Write WebSearch
---

# Debug Skill

You are debugging an issue in a React Native (Expo) + Firebase project. Follow this systematic approach.

## Phase 1: Understand the Problem

1. **Clarify the issue** — What exactly is happening vs. what's expected? Ask the user if anything is unclear.
2. **Gather context** — When did it start? Is it reproducible? What changed recently?

## Phase 2: Reproduce & Isolate

1. **Check for TypeScript errors:**
   ```bash
   npm run typecheck
   ```
2. **Run tests to see if anything breaks:**
   ```bash
   npm test
   ```
3. **Check Expo health:**
   ```bash
   npx expo-doctor
   ```
4. **Look at recent changes:**
   ```bash
   git log --oneline -10
   git diff HEAD~3 --stat
   ```

## Phase 3: Investigate

1. **Read the error message carefully** — Parse stack traces to find the originating file and line.
2. **Trace the code path** — Follow the execution from entry point to the error.
3. **Check common React Native / Expo pitfalls:**
   - Missing `key` props in lists
   - State updates on unmounted components
   - Async operations without proper error handling
   - Firebase `onSnapshot` listeners not being cleaned up
   - Navigation params mismatch
4. **Check Firebase-specific issues:**
   - Firestore security rules blocking reads/writes
   - Auth state not being ready before data fetches
   - Missing indexes for compound queries
5. **Use Grep to search** for related error messages, similar patterns, or the affected function across the codebase.

## Phase 4: Fix

1. **Identify the root cause** — Don't just fix symptoms.
2. **Make the minimal fix** — Change only what's needed.
3. **Verify the fix:**
   - `npm run typecheck` passes
   - `npm test` passes
   - If UI-related, test on device/simulator

## Phase 5: Prevent

1. **Add a test** if the bug was in untested logic.
2. **Check for similar issues** elsewhere in the codebase.

## Output

Report:
- **Root cause** — What actually caused the issue
- **Fix applied** — What was changed and why
- **Verification** — How you confirmed it's fixed
- **Risk assessment** — Could this affect other areas?
