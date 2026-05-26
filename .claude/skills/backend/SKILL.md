---
name: backend
description: Backend and Firebase service work — Firestore rules, cloud functions, service layer, data modeling, and API integration.
argument-hint: "[what-to-work-on]"
allowed-tools: Bash Read Grep Glob Edit Write Agent WebSearch
---

# Backend Skill

You are working on the backend layer of a React Native (Expo) + Firebase app.

## Architecture Overview

- **Backend:** Firebase (Auth, Firestore, Storage)
- **Firestore hierarchy:** `users/{userId}/` with subcollections: `vehicles`, `expenses`, `parkingSessions`, `incomes`, `receipts`, `notifications`, `settings`
- **Top-level:** `adminStats` collection
- **Storage:** `receipts/{uid}/{expenseId}/{timestamp}.jpg`
- **Service pattern:** Stateless functions in `*Service.ts` files per feature domain

## Key Files

| File | Purpose |
|------|---------|
| `src/config/firebase.ts` | Firebase initialization (Auth, Firestore, Storage) |
| `src/features/*/service*.ts` | Feature-specific Firestore CRUD and subscriptions |
| `src/features/*/*Validation.ts` | Zod schemas for input validation |
| `src/features/*/*Types.ts` | TypeScript interfaces/types |
| `firestore.rules` | Firestore security rules |
| `storage.rules` | Storage security rules |

## Tasks You Can Handle

### Firestore Service Layer
- Create/modify service functions for CRUD operations
- Add `onSnapshot` real-time subscriptions
- Implement compound queries with proper indexing
- Handle batch writes and transactions

### Data Modeling
- Design TypeScript interfaces for new collections
- Create Zod validation schemas
- Plan Firestore document structure (denormalization trade-offs)

### Security Rules
- Read/write `firestore.rules` and `storage.rules`
- Ensure user-scoped access (`request.auth.uid == userId`)
- Test rules with the Firebase emulator

### Receipt AI Pipeline
- `scripts/receipt-ai-server.mjs` — Gemini-powered parsing server
- `src/utils/receiptParser.ts` — Local regex fallback parser
- ML Kit OCR → Gemini → structured data flow

### Background Tasks
- Parking detection background task (`src/features/parking/`)
- AsyncStorage state management for background processes

## Conventions

1. **Always validate inputs** with Zod before Firestore writes.
2. **Use `onSnapshot`** for real-time data, not one-time `get` calls.
3. **Clean up listeners** — return unsubscribe from `useEffect`.
4. **Error handling** — catch and log Firestore errors, don't let them crash the app.
5. **Types first** — define TypeScript interfaces before implementing services.
6. **No business logic in components** — keep it in service files.

## Verification

After changes:
```bash
npm run typecheck    # Type safety
npm test            # Unit tests
npx expo-doctor     # Dependency health
```
