---
name: review
description: Code review for quality, security, and correctness. Use when reviewing code changes, PRs, or specific files.
argument-hint: "[file-path-or-pr-number]"
allowed-tools: Bash Read Grep Glob Agent WebSearch
---

# Review Skill

You are reviewing code in a React Native (Expo) + Firebase project. Be thorough but constructive.

## Review Checklist

### 1. Correctness
- Does the code do what it's supposed to?
- Are edge cases handled (null, undefined, empty arrays, network errors)?
- Are async operations properly awaited and error-handled?
- Are Firestore queries using the correct collection paths?

### 2. Security
- **Firebase rules:** Are reads/writes properly scoped to the authenticated user?
- **Input validation:** Is user input validated with Zod before Firestore writes?
- **Sensitive data:** No secrets, API keys, or tokens in code (should be in `.env` with `EXPO_PUBLIC_` prefix)
- **Auth checks:** Are protected routes/services verifying authentication?
- **XSS/Injection:** Any unsanitized user input in UI or queries?

### 3. Architecture & Patterns
- Follows the feature-module pattern (`src/features/<domain>/`)?
- Types defined in `*Types.ts`?
- Validation in `*Validation.ts` with Zod?
- Service layer in `*Service.ts`?
- Hooks in `use*.ts(x)`?
- Uses `COLORS`/`SHADOWS` from `constants.ts` (no hardcoded hex)?
- 8px grid spacing system followed?
- No global state management (except auth context)?

### 4. Performance
- Firestore listeners cleaned up in `useEffect` return?
- Lists using `keyExtractor` properly?
- Images optimized (appropriate size, lazy loading)?
- Avoiding unnecessary re-renders (proper dependency arrays)?
- Large lists using `FlatList` not `ScrollView`?

### 5. TypeScript
- Proper types — no `any` unless justified?
- Type guards for external data?
- Navigation types match `navigationTypes.ts`?
- Service functions have proper input/output types?

### 6. Testing
- Business logic has unit tests?
- Zod schemas have validation tests?
- Edge cases covered?

## Output Format

For each issue found:
- **Severity:** Critical / Warning / Suggestion
- **File:** `path/to/file.ts:line`
- **Issue:** What's wrong
- **Fix:** How to fix it

End with a summary: overall quality, merge readiness, and key concerns.
