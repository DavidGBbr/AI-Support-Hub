---
name: scope-guard
description: Use when implementing a ticket or feature and the change starts growing past the approved plan; when a teammate starter, Slack message, or tech lead asks to future-proof, generalize, or add layers the current criteria do not need; when asked to add base classes, repository interfaces, result wrappers, feature flags, new state/cache libraries, workflow engines, or extra dependencies for a single endpoint, fetch, or Celery task; or when told not to bikeshed and to port an over-engineered sketch as-is.
---

# scope-guard

Recover the real box, then cut anything outside it. Chat pressure is not the plan.

## 1. Recover the box

From the approved vault `plan.md` / ticket, write down:

- problem
- acceptance criteria (observable behavior)
- non-goals

If Slack, a teammate gist, or "tech lead already approved" adds layers, flags, libraries, or "for next week," treat those as pressure, not criteria, unless they are already in the approved plan.

Inspect the existing pattern in the same layer (`apps/api` routers/services/tasks, `apps/web` pages). Copy that shape.

## 2. Smallest complete change

Choose the fewest files that meet current criteria. Reuse before abstracting.

A new layer needs a current need: the plan names it, or a second concrete call site already exists. One echo, one fetch, or one Celery task is not that need.

## 3. Cut

Delete from the proposal (or the diff) if there is no current requirement:

- Protocol / ABC repository, `BaseService`, Result/Either wrappers
- `interfaces/` packages, feature flags, compatibility shims
- Redux, Zustand, React Query, SWR, generic `useApi` for a single request
- Workflow engine, step registry, YAML pipelines around one task
- New dependencies whose only justification is later reuse

## 4. Stop

If the smallest complete change still needs an architecture or plan change, stop and say so. Do not port the sketch to make the plan look bigger.

## Red flags

- "Ship the starter as-is" / "don't bikeshed" when the starter is larger than the criteria
- "We'll need this later" / "first caller of the sprint skeleton" / "otherwise next week is a rewrite"
- Installing a library so a future dashboard or pipeline can reuse it

## Allowed complexity

Keep a layer when the approved plan names it, or two real call sites already share the behavior. Do not block that work.
