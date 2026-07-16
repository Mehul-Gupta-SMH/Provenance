---
name: ponytail
description: Minimal-diff discipline — make the smallest unit of change that satisfies the task, and nothing else. Use before writing any code change and when reviewing a diff for scope creep.
---

# Ponytail — Smallest Unit of Change

Tie everything back. No loose strands. Every diff must be the *smallest unit of
change* that completes the stated task — nothing more.

## Rules

1. **One task, one diff.** A change belongs in the diff only if the task cannot
   be completed without it. If you can't trace a hunk back to the task
   statement, delete the hunk.
2. **No drive-by changes.** Never reformat, rename, reorder imports, fix
   unrelated typos, "improve" comments, or refactor adjacent code you happen to
   pass through — even if it looks wrong. Note it in your report instead.
3. **Additive over invasive.** Prefer adding a new function/file over modifying
   a shared one. Prefer modifying one function over changing a signature that
   ripples to callers. Change contracts (schemas, base classes, public
   signatures) only when the task explicitly requires it.
4. **Touch only allowlisted files.** If a task lists the files you may touch,
   that list is a hard boundary. Needing another file means stop and report —
   not edit.
5. **Match the surroundings.** New code copies the local style: naming, import
   grouping, docstring shape, error-handling idiom. A minimal diff reads as if
   the original author wrote it.
6. **No new dependencies** unless the task names them. No new config keys,
   env vars, or CLI flags unless required by the task.
7. **No speculative generality.** Do not add parameters, hooks, abstractions,
   or "for later" scaffolding the current task doesn't use. (Extension points
   defined in PLAN.md/CLAUDE.md are the task when they say they are.)

## Self-check before finishing (mandatory)

Run `git diff --stat` and `git diff` on your work and answer:

- [ ] Can every changed hunk be justified by one sentence tying it to the task?
- [ ] Would reverting any single hunk break the task? If not, revert it.
- [ ] Are there whitespace/format-only hunks? Remove them.
- [ ] Did any file outside the allowlist change? Restore it (`git checkout -- <file>`).
- [ ] Is the diff the smallest you could defend in review? If unsure, shrink it.

Report any needed-but-out-of-scope changes as notes for the orchestrator; do
not make them.
