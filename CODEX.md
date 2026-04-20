# Codex Workflow Guide

This file exists to keep future tasks fast, deterministic, and low-noise.

## Core Rules

1. Read narrowly first.
   - Start with `rg` or exact symbol search.
   - Open only the file blocks needed for the task.
   - Avoid full-file reads unless the file is small or clearly central.

2. Prefer deterministic checks over UI checks.
   - Use shell commands, HTTP requests, DB queries, and local tests first.
   - Use browser automation only when authenticated dashboards are the only path.

3. Validate locally before deploying.
   - Run targeted local checks for the exact files and flows changed.
   - Do one live smoke test only after local confidence is high.

4. Cap polling and retries.
   - Do not poll deployments endlessly.
   - Use bounded retries with backoff.
   - Stop once a result is conclusive.

5. Keep output concise.
   - Commentary updates should be short and high-signal.
   - Final responses should focus on changed files, verification, blockers, and next steps.

6. Avoid repeated repo discovery.
   - Track touched files, verified flows, and blockers during the task.
   - Do not re-open unchanged files unless a new dependency points back to them.

## Standard Task Flow

1. Locate the exact implementation area with `rg`.
2. Read only the relevant file sections.
3. Make the smallest coherent change.
4. Run focused local validation.
5. Deploy only if needed.
6. Run one bounded live smoke check if the task requires it.

## Deployment Rules

- Prefer service endpoints and logs over browser checks.
- If a deploy must be monitored, use a scripted status check.
- Re-check only after a meaningful wait or trigger.

## Validation Rules

- Re-run only tests affected by touched code.
- Do not repeat passing checks unless the code path changed.
- Prefer API-level smoke tests over full browser walkthroughs.

## Browser Use Policy

Use browser automation only for:
- Render environment/config actions
- GitHub/hosted dashboards requiring active login
- Dodo or other third-party dashboards requiring manual-session access

Do not use browser automation for:
- Simple endpoint verification
- Static page availability checks
- Repo inspection
- Local workflow steps that shell/API can prove directly

If a task depends on authenticated third-party dashboards and deterministic access fails after one focused attempt:
- stop the loop
- ask the user for the missing credential, key, or manual action
- resume with the smallest possible follow-up step

## Lightweight Working Notes

For larger tasks, keep a compact running note with:
- Active goal
- Files touched
- Checks passed
- Open blockers

Do not turn notes into a long journal.
