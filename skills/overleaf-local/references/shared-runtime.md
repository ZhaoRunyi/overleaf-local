# Shared code and local deployments

`assets/runtime/` is the single executable implementation. `scripts/configure.py` defaults to `local/ID/` inside the installed skill. That directory contains config, lightweight Python/extension entry points, a `repo` link to the manuscript, a `runtime` link to shared code, extension metadata, and a hook fragment. Distinct IDs have distinct command namespaces, sockets, pause records, and daemon locks. Never run two deployments for the same repository.

Never publish `local/`: it contains machine-specific project paths and configuration. The release repository ignores it. Keep credentials in the existing credential helper, not in the skill. Runtime sockets and logs remain under `/tmp`.

The installed skill is a runtime dependency, not a disposable installer. Preserve `local/` during upgrades. Pause affected services, test the candidate shared code in `/tmp`, install the tested code, restart services, and reload editor extensions. All linked projects consume shared updates, so verify each active configuration before resuming. Moving the skill requires regenerating the launchers and extension packages.

## Authorized migration

1. Inspect the actual deployment, editor connections, config, pause state and source status. Compare it against shared code; preserve deployment-specific fixes.
2. Run `scripts/regression_shared.py` with host Unix-socket access. It tests two isolated deployments sharing one runtime, synchronization, editor vetoes and mock conflict UI, not live GUI acceptance.
3. Preserve repository, remote, branch, allowlist, runtime directory, pause filename and extension namespace. `link_runtime()` in `configure.py` accepts an existing config and extension manifest. Supply `pause_name` and `command_namespace` for legacy deployments. Do not change manuscript content.
4. Pause the old service, install the new deployment and extension package, and update only its hook commands and documented tool paths. Preserve unrelated hooks. Changed hooks may require client review; never mark them trusted yourself.
5. Stop only the old project daemon, start the new one on the same lock/socket, and retain any conflict pause. Before resuming a previously clean service, verify editor readiness.
6. Clients may cache old paths. Retain a temporary compatibility symlink until they reload and actual hook/editor invocations confirm the new path. Cached old UI activity is not new-extension acceptance. Remove the link only after verification.
7. Verify real remote source status and actual editor protection. Use disposable projects for deliberate conflict/race tests. Report reload, hook review and web-side round trips separately. A read-only network check does not test a new upload.

Shared `build_paper.py` retains the `main.tex`/latexmk PDF workflow and accepts `tex_bin` in config. It does not automatically select the correct compiler for every conference; verify compiler and TeX Live before using it for another paper.
