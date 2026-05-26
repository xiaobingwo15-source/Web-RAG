---
name: feature-dev
description: End-to-end feature development workflow. Use when building a new feature from scratch.
argument-hint: "[feature-description]"
allowed-tools: Bash Read Grep Glob Edit Write Agent WebSearch AskUserQuestion EnterPlanMode ExitPlanMode
---

# Feature Development Skill

You are building a new feature for a React Native (Expo) + Firebase app. Follow this structured workflow.

## Phase 1: Plan

1. **Clarify requirements** with the user if anything is ambiguous.
2. **Check existing code** for reusable patterns:
   - Similar features in `src/features/*/`
   - Shared components in `src/components/ui/`
   - Utility functions in `src/utils/`
   - Constants and design tokens in `src/config/constants.ts`
3. **Design the data model:**
   - What Firestore collections/documents are needed?
   - What are the TypeScript types?
   - What validation (Zod) is needed?
4. **Plan the implementation** — get user approval before coding.

## Phase 2: Scaffold

1. **Create feature directory:** `src/features/<domain>/`
2. **Create type definitions:** `<domain>Types.ts`
   ```typescript
   export interface <Domain> {
     id: string;
     userId: string;
     // ... fields
     createdAt: Date;
     updatedAt: Date;
   }
   ```
3. **Create validation:** `<domain>Validation.ts`
   ```typescript
   import { z } from 'zod';
   export const create<Domain>Schema = z.object({ /* ... */ });
   ```
4. **Create service:** `<domain>Service.ts`
   - Firestore CRUD operations
   - `onSnapshot` subscriptions
   - All writes go through Zod validation first
5. **Create hooks:** `use<Domain>.ts`
   - Subscribe to Firestore with `onSnapshot`
   - Return `{ data, loading }` pattern

## Phase 3: Build UI

1. **Use design system:**
   - `Screen` component from `src/components/ui/Screen.tsx`
   - `COLORS`, `SHADOWS`, `BORDER_RADIUS` from `constants.ts`
   - Inter font family (Bold for headings, Medium for body)
   - 8px grid spacing (`gap: 16`, `padding: 24`)
   - Card radius: 12-16px
2. **Build screens** in the feature's `components/` directory or directly in the screen file.
3. **Wire navigation:**
   - Add to appropriate tab navigator in `src/navigation/`
   - Update `navigationTypes.ts`

## Phase 4: Integrate

1. **Connect UI to hooks** — use the feature's hooks in screen components.
2. **Handle loading/error states** — show appropriate UI for loading, empty, and error states.
3. **Add pull-to-refresh** if data-driven.

## Phase 5: Verify

1. **TypeScript:** `npm run typecheck`
2. **Tests:** `npm test`
3. **Expo health:** `npx expo-doctor`
4. **Manual test** on device/simulator if possible.

## Output

Report what was built:
- Files created/modified
- Data model design
- Navigation changes
- Any open questions or follow-ups
