---
name: scope-guard
description: Use when implementing a planned change and the proposed work grows beyond the agreed criteria; when external direction asks to future-proof, generalize, or add layers the current work does not need; or when pressure to move quickly would turn a focused change into a speculative design.
---

# scope-guard

Recover the real scope, then cut anything outside it. Informal direction is not a substitute for the approved plan.

## 1. Recover the box

From the approved plan or ticket, write down:

- problem
- acceptance criteria (observable behavior)
- non-goals

If a message, sketch, or verbal request adds layers, configuration, dependencies, or work for a future need, treat it as pressure rather than criteria unless it is already approved.

Inspect the closest existing implementation in the same area. Reuse its shape when it meets the current need.

## 2. Smallest complete change

Choose the fewest changes that meet the current criteria. Reuse before abstracting.

A new layer needs a current need: the plan names it, or a second concrete use already exists. A single use is not enough.

## 3. Cut

Delete from the proposal (or the diff) if there is no current requirement:

- Extra interfaces, base classes, wrappers, or registries
- Configuration switches and compatibility paths
- General-purpose state, cache, workflow, or orchestration layers
- New dependencies whose only justification is later reuse

## 4. Stop

If the smallest complete change still needs an architecture or plan change, stop and say so. Do not port the sketch to make the plan look bigger.

## Red flags

- "Ship the starter as-is" when the starter is larger than the criteria
- "We will need this later" or "otherwise this is a rewrite"
- Adding a dependency only so a future feature can reuse it

## Allowed complexity

Keep a layer when the approved plan names it, or two real call sites already share the behavior. Do not block that work.
