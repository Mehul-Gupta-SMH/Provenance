---
name: ponytail
description: Lazy-developer minimalism (after github.com/DietrichGebert/ponytail) — write the least code that works and make the smallest unit of change. Use before writing any code and when reviewing a diff for over-engineering or scope creep.
---

# Ponytail — The Best Code Is the Code You Never Wrote

Adapted for this repo from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail).
Be lazy about solutions — never about requirements. Read the task fully, then
write as little as possible to satisfy it.

## The Decision Ladder (stop at the first rung that applies)

Before writing ANY code, climb this ladder and stop at the first "yes":

1. **Does this need to exist at all?** If the task doesn't require it — don't write it.
2. **Already in this codebase?** Reuse the existing function/pattern/helper. Search first.
3. **Stdlib does it?** `json`, `urllib.parse`, `functools`, `itertools`, `re`, `statistics` — before any hand-rolled version.
4. **Native platform feature?** FastAPI/SQLModel/Pydantic built-ins (Depends, response_model, validators, table constraints) before custom plumbing.
5. **Installed dependency does it?** Use what's already in requirements.txt. Never add a new dependency for something an installed one does.
6. **One line?** If a one-liner is clear, ship the one-liner.
7. **Only then:** write the minimum that works.

## Smallest Unit of Change

- **One task, one diff.** Every hunk must trace to the task statement in one sentence. Untraceable hunk → delete it.
- **No drive-by changes.** No reformatting, renames, import reshuffles, comment "improvements", or refactors of adjacent code. Note them in your report instead.
- **Additive over invasive.** New function over modifying a shared one; local change over signature change that ripples. Contracts (schemas, base classes, public signatures) change only when the task says so.
- **Hard file allowlists.** If the task lists files you may touch, that list is a boundary. Needing another file = stop and report.
- **Match the surroundings.** Minimal diffs read as if the original author wrote them.
- **No speculative generality.** No parameters, hooks, or abstractions the current task doesn't use. (Extension points mandated by PLAN.md/CLAUDE.md are part of the task.)

## Never on the Chopping Block

Laziness never applies to:

- **Trust-boundary validation** — validate all external input (API bodies, LLM output, scraped data).
- **Data-loss handling** — transactions, error paths that leave state consistent.
- **Security** — no secrets in code, no injection vectors, no disabled verification.
- **Requirements** — read the whole task; lazy code, never lazy reading.

## Self-check before finishing (mandatory)

Run `git diff --stat` and `git diff` on your work:

- [ ] Could any hunk be replaced by something that already exists (codebase/stdlib/framework)?
- [ ] Would reverting any single hunk still satisfy the task? Then revert it.
- [ ] Any abstraction with exactly one caller? Inline it.
- [ ] Any whitespace/format-only hunks? Remove them.
- [ ] Any file outside the allowlist changed? Restore it.
- [ ] Is anything on the never-lazy list (validation/data/security) skipped? Fix that — it is not optional.

Report needed-but-out-of-scope changes as notes for the orchestrator; do not make them.
