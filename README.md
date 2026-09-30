# overleaf-local

A Codex skill for protected bidirectional synchronization between an Overleaf Git project and local
LaTeX sources, including multi-window editor guards, explicit conflict resolution, Codex edit guards,
and PDF identity checks.

This repository contains one skill at `skills/overleaf-local`. It is **not** a Codex plugin.

## Install

Ask Codex:

```text
Use $skill-installer to install ZhaoRunyi/overleaf-local from path skills/overleaf-local.
```

Restart Codex and invoke `$overleaf-local` for a new or existing paper. The configurator generates a
project-specific runtime; it does not clone, publish, install a VSIX, overwrite hooks, or choose a
conflict side without authorization.

For pixel-level PDF comparison, install the optional Pillow runtime and ensure Poppler is available:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/overleaf-local/scripts/bootstrap_runtime.sh"
```

For quiet-source wake after remote edits settle, also install
[`codex-bg`](https://github.com/ZhaoRunyi/codex-bg) and
[`codex-wake`](https://github.com/ZhaoRunyi/codex-wake). Ordinary source synchronization does not
depend on them.

## Supported scope

The tested runtime targets Linux/POSIX with Git, Python 3.10+, `screen`, and VS Code's remote
extension host. Overleaf Git access and local credential configuration are required. Credentials,
paper contents, generated deployments, runtime sockets, and synchronization logs do not belong in
this repository.
