# AGENTS.md

Project-level instructions for AI coding agents working in this repository.

@/home/papajittan/.codex/RTK.md

## Session Continuity

Every agent session must use `progress.md` as the project handoff log.

- Before continuing the project, read `progress.md` completely.
- If `progress.md` does not exist, create it before making project changes.
- At the start of a session, summarize the current state from `progress.md` in your own working context.
- During the session, update `progress.md` whenever scope, implementation status, decisions, blockers, commands, or verification results change.
- Track elapsed session time. If approaching a 5-hour execution limit, stop new implementation work early enough to update handoff notes, record verification status, and leave the repository in a coherent state.
- Do not run into the 5-hour limit with unrecorded work. Prefer stopping around the 4-hour 30-minute mark, or earlier if the remaining work cannot be finished and documented safely.
- At the end of every session, update `progress.md` with:
  - current objective
  - files changed or created
  - completed work
  - pending work
  - commands/checks run and their results
  - known blockers, assumptions, or risks
- Keep `progress.md` concise, factual, and append-friendly. It should let the next agent resume without re-reading the entire conversation.
- Do not treat `progress.md` as a substitute for source files, tests, or the user prompt. It is a navigation aid and handoff record.

## Markdown Records

Keep project markdown files current with the present state of the work.

- Update relevant markdown files whenever the project reality changes: `progress.md`, `context.md`, `README.md`, planning docs, runbooks, and any other handoff or design notes.
- `progress.md` is the session log and should change most often.
- `context.md` is the stable project brief; update it when product scope, architecture, data assumptions, pipeline behavior, or major decisions change.
- Do not leave markdown claiming files, features, commands, tests, or blockers that are no longer true.
- When implementation changes create new setup, run, data, or verification steps, document them in the appropriate markdown file during the same session.
- Keep markdown concise and factual. Prefer clear status and next steps over narrative transcripts.

## Behavioral Guidelines

These guidelines reduce common coding-agent mistakes. They bias toward careful,
small, verified changes. For trivial tasks, use judgment.

## 1. Think Before Coding

Do not assume silently. Surface uncertainty and tradeoffs.

- State meaningful assumptions before acting.
- If the request has multiple plausible interpretations, ask or briefly name the path you are taking.
- Push back when requirements are unclear, risky, or internally inconsistent.
- Prefer a simple, direct approach when it satisfies the request.

## 2. Simplicity First

Write the minimum code that solves the actual problem.

- Do not add speculative features, configuration, or abstractions.
- Do not generalize single-use code without a concrete need.
- Avoid defensive branches for scenarios the system cannot produce.
- If a solution is growing large, look for the smaller shape before continuing.

## 3. Surgical Changes

Touch only what the task requires.

- Match existing style, structure, and naming.
- Do not refactor adjacent code just because it is nearby.
- Do not reformat unrelated files or rewrite stable code paths.
- Remove only dead imports, variables, functions, or files created by your own change.
- Mention unrelated issues you notice instead of fixing them unless asked.

Every changed line should trace back to the user's request.

## 4. Goal-Driven Execution

Turn work into verifiable outcomes and loop until checked.

- For bug fixes, reproduce the failure before fixing when practical.
- For new behavior, add or update focused tests when the repo has a test pattern.
- For refactors, verify behavior before and after when feasible.
- For multi-step work, keep a short plan with an explicit verification step.
- Before claiming completion, run the relevant checks or state exactly why they could not be run.

Good outcomes: small diffs, fewer unnecessary rewrites, explicit uncertainty, and verified behavior.
