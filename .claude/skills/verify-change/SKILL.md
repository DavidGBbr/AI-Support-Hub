---
name: verify-change
description: Use when finishing a change, before claiming completion or opening a pull request; when selecting checks for the actual diff; after edits to application code, configuration, automation, data definitions, or operational documentation; or when pressure would replace evidence with assumption.
---

# verify-change

Map the real diff to the project's documented checks. Urgency is not a skip list.

## 1. Map the diff to checks

Read the actual diff, then consult the project's contribution guide, automation, and nearby documentation. Identify the checks that cover each changed area.

Run only the checks relevant to the areas changed. For data definitions, include the documented validation or migration step. For configuration and operational changes, validate the configuration or execution path they affect. For documentation changes, reread the rendered instructions and confirm referenced paths and commands exist.

Do not run unrelated suites to look busy. Do not skip a mapped check because automation will catch it, a prior run looked healthy, or someone asks to hurry.

## 2. Inspect the diff

Before completion, scan for scope creep, duplication, new dependencies, undocumented configuration, data changes without an execution note, and missing documentation when behavior, contracts, commands, or operations changed.

## 3. Report

List each check, where it ran, and its exit status. List skipped checks with the reason. Never invent passing output. Never claim completion with a failing check. A check that did not run is not green.

If a mapped check cannot run, report the limitation and do not describe the change as fully verified.
