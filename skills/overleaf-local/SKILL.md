---
name: overleaf-local
description: Set up, reuse, troubleshoot, and verify protected bidirectional synchronization between an Overleaf Git project and local LaTeX files, with VS Code conflict resolution, Codex edit guards, and optional same-thread wake after remote edits settle. Use for paper synchronization and deployment, not ordinary manuscript editing.
---

# Overleaf Local

Build a project-scoped workflow from the bundled, tested runtime. It includes saved-file synchronization, multi-window editor protection, explicit local/Overleaf conflict choices, edit guards, and optional stable-source wake. Do not migrate a working project merely to install this skill.

## Scope and authority

- Ask for the local canonical directory, Overleaf project/Git URL, main TeX file, and upload allowlist. Confirm Git integration access. Never ask the user to paste a token in chat; configure credentials locally.
- Reading and diagnosing a project does not authorize publishing, choosing a conflict side, removing files, or altering manuscript text. Obtain authorization for initialization/first push and any reconciliation choice.
- Preserve existing repositories, editors, credential helpers, hooks, LaTeX recipes, source names, and project conventions. Never force-push or reset to resolve divergence.
- Runtime support is Linux/POSIX with Git, Python 3.10+, screen, and VS Code's remote workspace extension host. A Windows editor can connect to that host. Native Windows/macOS daemons require a separately tested port; do not promise support from these scripts.

## Routes

1. **Existing deployment:** locate its config, inspect status and pause record, then read [operations.md](references/operations.md). Reuse the installed engine; do not start a second daemon for the same repository.
2. **New paper:** read [setup.md](references/setup.md). Reconcile the repository and allowlist first, then generate a project-specific deployment with `scripts/configure.py`. This script only creates tools and packages; it does not clone, stage, commit, push, install extensions, overwrite user hooks, or arm a watcher.
3. **Conflicts or slow UI:** read [operations.md](references/operations.md). The conflict UI uses local snapshots; fetch only on refresh/final submission. Draft choices never publish without confirmation.
4. **Codex protection and wake:** read [codex-and-wake.md](references/codex-and-wake.md). Trust hooks through the actual client, verify their invocation, and use the available `codex-wake` skill for a live wait. Polling without successful same-thread delivery is not acceptance.
5. **Acceptance/PDF identity:** read [verification.md](references/verification.md). Run `scripts/regression.py` against a generated deployment in `/tmp`, then separately verify authorized real transport and UI. Use `scripts/compare_pdfs.py` for supplied local and Overleaf PDFs; do not infer PDF equality from equal source alone.

## Non-negotiable synchronization properties

- Dedicated canonical repository and explicit tracked-file allowlist; no secrets, chat histories, tools, temporary artifacts, or unrequested build outputs.
- One serialized daemon per project, distinct project command namespaces/sockets, non-forced pushes, temporary trial merges, and CAS ref updates.
- Check every connected window before remote writes. Unsaved/busy/stale buffers block application. Do not choose an owner window or discard another window's input.
- Conflicts preserve both versions and pause. Use native three-way merge or explicit whole-file local/Overleaf choice, followed by a final confirmation. Revalidate remote revision and local source before applying a draft.
- Saved-file debounce and remote polling are best-effort, not keystroke synchronization. Network retries back off. Source synchronization does not trigger or prove Overleaf PDF compilation.
- Git history is not a guarantee of one matching recoverable Overleaf History node per commit. Do not promise comment/Track Changes round-trip preservation.
- Codex stale-source retries stop after ten checks; reread synchronized source before reconstructing a patch. Do not disable the guard to bypass a conflict. Only arm a quiet watcher for an actual unfinished authorized task.

## Delivery

Report the project config, GUI entry points, credential persistence choice, source scope, timings measured separately from polling frequency, and test evidence. Distinguish isolation tests, actual editor tests, actual network round trips, PDF rendering checks, and user-only acceptance. Clearly identify unfinished checks; do not label a mock test an end-to-end success.
