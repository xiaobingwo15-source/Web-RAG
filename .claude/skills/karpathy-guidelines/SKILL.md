---
name: karpathy-guidelines
description: Use when implementing code changes to ensure surgical, simple, and goal-driven execution following Andrej Karpathy's coding pitfalls guidelines.
---

# Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from Andrej Karpathy's observations.

## 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

- **State assumptions explicitly.** If uncertain, ask.
- **Present interpretations.** If multiple exist, don't pick silently.
- **Propose simpler approaches.** Push back when warranted.
- **Stop if unclear.** Name what's confusing and ask.

## 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

- **No features beyond what was asked.**
- **No abstractions for single-use code.**
- **No "flexibility" or "configurability" that wasn't requested.**
- **No error handling for impossible scenarios.**
- **Senior Engineer Test:** "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes
Touch only what you must. Clean up only your own mess.

### When editing existing code:
- **Don't "improve" adjacent code,** comments, or formatting.
- **Don't refactor** things that aren't broken.
- **Match existing style,** even if you'd do it differently.
- **Mention dead code** if noticed, but don't delete unless it's yours.

### When your changes create orphans:
- **Remove imports/variables/functions** that YOUR changes made unused.
- **Don't remove pre-existing dead code** unless asked.

## 4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:
- **Validation:** "Write tests for invalid inputs, then make them pass"
- **Bug Fix:** "Write a test that reproduces it, then make it pass"
- **Refactor:** "Ensure tests pass before and after"

### Plan-Act-Verify Loop:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
