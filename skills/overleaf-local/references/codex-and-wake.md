# Codex edit guards and stable-source wake

The generated hook fragment contains PreToolUse and PostToolUse entries. Merge it into the client's supported configuration without replacing unrelated hooks. The client must trust/enable them. Hook APIs and tool-name envelopes vary; check current official documentation and test the actual VS Code/CLI client. This skill cannot guarantee interception of tools that bypass that hook interface.

The guard scopes patches to allowlisted paper files. Before a patch it checks synchronization, editor protection, and the source revision last read by this session. After a patch it requests synchronization. It denies shell mutation of manuscript files and directs the agent to `apply_patch`. Read detection is a practical guardrail for recognized shell reads, not a complete filesystem monitor: explicitly reread affected files before edits and do not treat recorded HEAD as proof that every line was read.

Verify `/tmp/overleaf-local-UID-ID/hook-audit.jsonl` records invocation from the actual client. Testing the Python hook with fabricated input alone proves only handler behavior. If a tool invocation is not intercepted, do not assert protection: use explicit pre-edit check and reread, then fix the client integration before enabling unattended edits.

## Bounded retry and continuation

Ten successive source-change checks stop the current edit loop. Do not disable the guard, freeze another author's session, or keep retrying indefinitely. Explain that changes remain uncommitted/unapplied and arrange continuation only for an already-authorized unfinished task.

Use the installed `codex-wake` skill for the full workflow; read its SKILL.md before arming anything. `arm_quiet_watch.py` is a project-aware adapter, not a replacement for wake setup and delivery verification. It requires an exact thread/session ID and task-specific continuation prompt. The dependency path is in `config.json`. If absent, report missing wake support; ordinary source synchronization remains independent.

The probe is read-only and asks the daemon for readiness: 90 seconds of observed unchanged remote HEAD, recent polling, synchronized source, no pending local changes/conflicts, and a clean connected editor. This measures observed source stability, not proof that nobody is currently typing in the browser. An uncommitted web edit can only be observed when exposed by Overleaf Git.

Inspect the helper with `--help`; dry-run first, then arm via the dependency's persistent watcher. Confirm status AND same-thread delivery. On wake, recheck synchronization, reread source, and reconstruct the patch. The prompt must preserve task scope; a watcher must not invent a paper edit when only infrastructure acceptance was authorized.

Runtime state is under `/tmp`, so container reboot may lose sockets, read markers, and detached sessions. Restore the daemon/editor first and use the wake skill's documented persistence behavior. Do not represent a `screen` session as a cross-reboot service.
