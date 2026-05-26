---
name: frontend
description: Frontend and UI work — screens, components, navigation, styling, and user experience.
argument-hint: "[what-to-work-on]"
allowed-tools: Bash Read Grep Glob Edit Write Agent WebSearch
---

# Frontend Skill

You are working on the frontend of a React Native (Expo) app with a "Bento" design philosophy.

## Design System

### Colors & Tokens (from `src/config/constants.ts`)
- Always use `COLORS`, `SHADOWS`, `BORDER_RADIUS` — never hardcode hex values
- Background, surface, primary, secondary, text colors are all tokenized

### Typography
- **Headings:** Inter-Bold, 24px+
- **Body:** Inter-Medium, 15px
- **Monospace:** For currency amounts and license plates
- Font family: `Inter-Bold`, `Inter-Medium`, `Inter-Regular`

### Spacing
- 8px grid system: `8, 12, 16, 20, 24, 32, 40, 48`
- Common: `gap: 16`, `padding: 24`, `marginBottom: 12`

### Cards & Surfaces
- Card radius: 12-16px
- Internal padding: 16-20px
- Use `SHADOWS` for elevation

### Bento Layout
- Grid-based, modular card layouts
- Each card is a self-contained information unit
- Visual hierarchy through size and spacing, not decoration

## Key Files

| File | Purpose |
|------|---------|
| `src/config/constants.ts` | Design tokens (COLORS, SHADOWS, BORDER_RADIUS) |
| `src/components/ui/Screen.tsx` | Reusable screen wrapper (safe area, scroll, pull-to-refresh) |
| `App.tsx` | Root component |
| `src/navigation/` | React Navigation v7 setup |

## Navigation

- React Navigation v7 with native stacks
- 6 tabs: Home, Expense, Parking, Reports, Income, Settings
- Each tab has its own native-stack navigator
- Types in `navigationTypes.ts`
- Global `navigationRef` for navigation outside components

## Component Patterns

### Screen Component
```tsx
import Screen from '@/components/ui/Screen';

<Screen scroll refreshControl={...}>
  {/* content */}
</Screen>
```

### Card Pattern
```tsx
<View style={{
  backgroundColor: COLORS.surface,
  borderRadius: BORDER_RADIUS.lg,  // 12-16
  padding: 20,
  ...SHADOWS.medium,
}}>
  {/* card content */}
</View>
```

### List Pattern
```tsx
<FlatList
  data={items}
  keyExtractor={(item) => item.id}
  renderItem={({ item }) => <ItemCard item={item} />}
  contentContainerStyle={{ gap: 12, padding: 24 }}
/>
```

## Tasks You Can Handle

- Build new screens and components
- Modify navigation structure
- Implement animations and gestures
- Style components following the design system
- Add pull-to-refresh, infinite scroll, etc.
- Handle loading/empty/error states
- Responsive layout adjustments

## Conventions

1. **Use design tokens** — `COLORS`, `SHADOWS`, `BORDER_RADIUS` from constants.
2. **8px grid** — All spacing should be multiples of 8 (or 4 for tight spaces).
3. **Safe area** — Always use `Screen` wrapper for proper safe area handling.
4. **Accessible** — Use `accessibilityLabel`, `accessibilityRole` on interactive elements.
5. **Performance** — `FlatList` for lists, memoize expensive components, avoid inline functions in render.
6. **TypeScript** — Proper types for all props, navigation params, and state.

## Verification

```bash
npm run typecheck    # Type safety
npm test            # Unit tests
npm run android     # Test on Android
```
