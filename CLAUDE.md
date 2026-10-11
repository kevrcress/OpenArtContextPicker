# OpenArtContextPicker

HVE is installed globally (`~/.claude/`). This file holds project context only.

## Your Project

A timed work sample: build `director-context.zip`, a Python 3.11 standard-library context picker for OpenArt's Director. Due 2026-10-11 15:30 PDT.

- `docs/task-brief.md`: the assignment text. `resources/task.md` is the same text as saved from the task page; it is not one of the five supplied resources.
- `docs/orchestrator-notes.md`: recorder constraints, quality bars, validation traps, corpus census, file hashes.
- `docs/research-prompt.md`: the research brief.
- `resources/`: supplied files. Never modify them. `resources/benchmark_inputs.json` is 8.4 MB; never Read it, use shell.

## Process

All work runs through the HVE RPI phase commands: `/hve-research`, `/hve-plan`, `/hve-implement`, `/hve-review`. Artifacts live in `.claude-hve-tracking/`. Task slug: `director-context-picker`.

Use `python3.11` by name. `python3` on this machine is 3.14.7.

## GitHub tracking

This project tracks HVE work in GitHub Issues — use the gh-tracker skill.

- Repo: `kevrcress/OpenArtContextPicker`
- Board: ContextPicker, `https://github.com/users/kevrcress/projects/5` (project number 5, owner `kevrcress`, project ID `PVT_kwHOABptxM4BmmZk`). Record it as `project` in the gh-tracker state file.
- Board workflows (verified 2026-10-11): new issues and sub-issues in this repo are added to the board automatically; closing an issue sets Status to Done; setting Status to Done closes the issue.

### Status meanings

| Status | Meaning |
|---|---|
| Backlog | Has an open blocker |
| Ready | Every blocker is closed and nobody has claimed it. Everything in Ready at the same moment can run in parallel |
| In progress | Claimed. A comment on the issue names the seat or subagent |
| In review | Delivered, awaiting verification |
| Done | Verified and closed. Never set Done by hand before verification, because it closes the issue |

### Field IDs (as of 2026-10-11)

| Field | Field ID | Options |
|---|---|---|
| Status | `PVTSSF_lAHOABptxM4BmmZkzhlOu_0` | Backlog `f75ad846`, Ready `e18bf179`, In progress `47fc9ee4`, In review `aba860b9`, Done `98236657` |
| Priority | `PVTSSF_lAHOABptxM4BmmZkzhlOvE8` | P0 `79628723`, P1 `0a877460`, P2 `da944a9c` |
| Size | `PVTSSF_lAHOABptxM4BmmZkzhlOvFA` | XS `911790be`, S `b277fb01`, M `86db8eb3`, L `853c8207`, XL `2d0801e2` |

Priority: P0 is a required deliverable or required contract behavior, P1 is a contract quality bar, P2 is an optional capability.

### Dependencies

Every plan phase states `Dependencies:` as phase numbers or `none`, and lists the files it owns. Two phases that can run in parallel never own the same file. After the phase sub-issues exist, mirror each dependency with `gh issue edit <child> --add-blocked-by <blocker>` (gh 2.94.0).
