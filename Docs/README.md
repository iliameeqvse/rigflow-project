# RigFlow Documentation

This folder is the long-form documentation for the RigFlow project. It is meant to be readable cold by someone who has never seen the codebase.

For Claude Code agent instructions and quick repo gotchas, see the top-level `CLAUDE.md` instead — it is intentionally terser and is loaded automatically into agent context.

## Where to start

| If you are… | Read in this order |
|---|---|
| New to the project | [PRODUCT_REQUIREMENTS](PRODUCT_REQUIREMENTS.md) → [ARCHITECTURE](ARCHITECTURE.md) → [DEVELOPMENT](DEVELOPMENT.md) |
| Setting up locally | [DEVELOPMENT](DEVELOPMENT.md) → [KNOWN_ISSUES](KNOWN_ISSUES.md) |
| Building against the HTTP API | [API](API.md) → [RIGGING_PIPELINE](RIGGING_PIPELINE.md) |
| Debugging the rig output | [RIGGING_PIPELINE](RIGGING_PIPELINE.md) → [KNOWN_ISSUES](KNOWN_ISSUES.md) |
| Planning the next feature | [RIGFLOW_PRD](RIGFLOW_PRD.md) → [ROADMAP](ROADMAP.md) |

## Contents

### Product
- [**PRODUCT_REQUIREMENTS.md**](PRODUCT_REQUIREMENTS.md) — short user-facing requirements summary.
- [**RIGFLOW_PRD.md**](RIGFLOW_PRD.md) — full PRD: scope, MVP cut-line, non-functional requirements, acceptance criteria.
- [**ROADMAP.md**](ROADMAP.md) — phased plan with concrete checklist items.

### Engineering
- [**ARCHITECTURE.md**](ARCHITECTURE.md) — services, request flow, storage layout, WebSocket channel.
- [**TECHNICAL_CONTEXT.md**](TECHNICAL_CONTEXT.md) — quick-reference of stack, dependencies, repo layout.
- [**RIGGING_PIPELINE.md**](RIGGING_PIPELINE.md) — Blender automation deep dive: landmarks, pose detection, rerig flows.
- [**API.md**](API.md) — REST endpoint reference, throttle table, error shapes.
- [**DEVELOPMENT.md**](DEVELOPMENT.md) — local setup, env vars, common commands, troubleshooting.
- [**KNOWN_ISSUES.md**](KNOWN_ISSUES.md) — repo gotchas, code drift, things that look broken but aren't (and things that are).

## Conventions

- All shell paths in these docs are relative to `rigflow-project/rigflow-project/` (the nested source root — see [KNOWN_ISSUES](KNOWN_ISSUES.md#repo-layout)).
- API examples use `http://localhost:8000` (Django dev server). In Docker the same port is served via Daphne behind Nginx.
- When adding a new doc, link it from this index and from any sibling doc whose readers would benefit. Keep the index entry to one line.
