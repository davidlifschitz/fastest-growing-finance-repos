# Ecosystem Integration Plan

## Role in the ecosystem

[fastest-growing-finance-repos](https://github.com/davidlifschitz/fastest-growing-finance-repos) should be the public finance intelligence and publishing pipeline in the ecosystem: discovery, ranking, reporting, and public distribution.

## Connected repos

- [agentic-os](https://github.com/davidlifschitz/agentic-os) — source of publish and artifact contracts
- [ScheduleOS](https://github.com/davidlifschitz/ScheduleOS) — should be able to trigger publishing, summaries, and status checks
- [children-of-israel-agent-swarm](https://github.com/davidlifschitz/children-of-israel-agent-swarm) — can support deeper finance research or derivative report generation
- [graphify](https://github.com/davidlifschitz/graphify) — should summarize pipeline structure and help future edits
- [davidlifschitz.github.io](https://github.com/davidlifschitz/davidlifschitz.github.io) — should link to this as a public flagship product
- [ShortcutForge](https://github.com/davidlifschitz/ShortcutForge) — can create quick open/report shortcuts for mobile access

## How this repo should connect

### 1. Emit structured machine-readable artifacts

In addition to Markdown and GitHub Pages output, this repo should emit a structured artifact such as:

- `artifacts/latest.json`
- `artifacts/archive/*.json`

Purpose:

- allow other systems to consume ranked outputs directly
- support summaries, republishing, and downstream analysis

### 2. Be triggerable from ScheduleOS

[ScheduleOS](https://github.com/davidlifschitz/ScheduleOS) should be able to ask:

- is the latest report published?
- what changed this week?
- republish or summarize latest output

### 3. Support deeper research via the swarm

For more advanced workflows, [children-of-israel-agent-swarm](https://github.com/davidlifschitz/children-of-israel-agent-swarm) should be able to take the structured ranking output and build longer reports, comparisons, or alerts.

## Files to add next

- `docs/pipeline-contract.md`
- `artifacts/latest.json`
- `artifacts/archive/.gitkeep`
- `docs/operator-actions.md`

## Example flow

1. ranking pipeline runs
2. public output is published to GitHub Pages
3. structured artifact is also written for machine use
4. [ScheduleOS](https://github.com/davidlifschitz/ScheduleOS) can summarize or report on the current state
5. [davidlifschitz.github.io](https://github.com/davidlifschitz/davidlifschitz.github.io) links to the live product

## Acceptance criteria

- this repo emits machine-readable output in addition to human-readable Pages content
- ScheduleOS-triggered operator actions are documented
- the repo is positioned as a reusable publishing pipeline for the broader ecosystem
