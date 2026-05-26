---
name: research-first
description: Use BEFORE designing any system or implementing features that involve external technologies, libraries, or APIs to ensure evidence-based technical decisions.
---

# Research First Protocol

## Overview

Never rely on training data for changing APIs or external libraries. Research first.

**Core principle:** Evidence before claims. Docs before code.

## The Protocol

You MUST complete these steps BEFORE proposing a design or implementation:

1. **Identify External Dependencies:** List all libraries, APIs, or external services involved.
2. **Search Online:** Use `google_web_search` to find the latest version, documentation, and best practices.
3. **Fetch Documentation:** Use `web_fetch` to read the official documentation or GitHub READMEs.
4. **Identify Breaking Changes:** Check for recent updates that might affect implementation.
5. **Present Findings:** Share links and key findings with the user BEFORE the design proposal.

## Implementation Rules

- **No Hallucinated APIs:** If you aren't 100% sure of a method signature, research it.
- **Version Awareness:** Explicitly mention which version of a library you are designing for.
- **Evidence-First Design:** Every architectural decision must be backed by current documentation.

## When to Use

- Adding a new dependency
- Using a library you haven't used in this session
- Integrating with an external API
- Encountering an error that seems library-specific
- Designing a new system or feature
