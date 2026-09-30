# New-project setup

## 1. Confirm scope and reconcile first

Obtain the canonical local paper path, Overleaf project/Git URL, main file, and explicit upload list. Read-only inspection comes first. Keep project IDs, paths, author metadata, TeX versions, and tokens out of the reusable template. This package does not grant Overleaf access.

Use one dedicated ordinary Git clone per paper, tracking only approved LaTeX sources, bibliography, style files, and figure assets. Do not auto-track directories or build outputs. Use the existing canonical repository if appropriate; otherwise clone into a new directory and reconcile with the user's local files. A first push or replacement of either side requires authorization. Never use force push, reset, or checkout to discard user edits. For unrelated histories, compare files in a separate directory and obtain a merge decision; do not auto-merge unrelated projects.

The generator requires its allowlist to match the existing tracked-file set exactly. It deliberately does not remove, add, or commit files to make the test pass. Reject symlinks. Ask before adding/removing a file from an established shared project. `.git/info/exclude` may exclude untracked local material without changing shared source, but only tracked approved files are uploaded.

## 2. Credentials

Prefer the user's existing persistent OS credential manager. On a headless host, if explicitly accepted by the user, Git's `store` helper persists credentials in plaintext: set the file owner-only and explain this tradeoff. Do not replace an existing helper globally without approval. Configure the helper consistently with the `--git-config` path passed to the generator. The credential-store file and config must never be in the paper or skill package.

For Overleaf Git, use username `git` and the user's Overleaf access token as the password, entered interactively in a terminal, never in chat, a remote URL, shell history, or generated config. Example verification (replace URL and config path):

```bash
env -u GIT_ASKPASS -u SSH_ASKPASS GIT_CONFIG_GLOBAL=/path/to/.gitconfig \
  git ls-remote --symref https://git@git.overleaf.com/PROJECT_ID HEAD
```

Repeat with `GIT_TERMINAL_PROMPT=0` to verify noninteractive authentication. Do not display `git credential fill`, credential files, environment dumps, or token-bearing URLs. Use the actual branch reported by HEAD, normally `main`.

## 3. Generate, inspect, install

Required host tools: Git, Python 3.10+, `screen`, VS Code remote extension host, and Node.js for optional UI regression checks. Set a unique short project slug and a persistent deployment directory OUTSIDE the manuscript repository. Temporary state remains in `/tmp`, while scripts/config persist.

Create an approved JSON file list using the normal patch tool, for example `["main.tex", "references.bib", "figures/pipeline.pdf"]`. Then run:

```bash
python /path/to/overleaf-local/scripts/configure.py \
  --id my-paper --repo /path/to/paper --out /path/to/paper-tools \
  --files /tmp/paper-files.json --git-config /path/to/.gitconfig
```

The script packages `/tmp/overleaf-local-my-paper.vsix` but does NOT install it, start a service, or modify manuscript files. Inspect `config.json`, `hooks.fragment.json`, and `extension/deployment.json`. Project-specific commands, snapshot schemes, runtime sockets, and extension IDs avoid cross-project collisions. Do not reuse an ID for another active deployment.

Install using the remote VS Code window's Extensions → Install from VSIX, or its own remote `code --install-extension /tmp/overleaf-local-my-paper.vsix`. Reload only after saving outstanding edits. Installing with the wrong local/remote CLI targets the wrong extension host. The deployment directory must remain accessible at its generated absolute path; regenerate/repackage before relocating it.

The extension activates for the configured repository or an ancestor workspace, opens an editor-protection socket, and launches `start.sh`. Alternatively, run `bash /path/to/paper-tools/start.sh`. Run host socket/screen operations in the host environment if the command sandbox isolates sockets. The service lock prevents duplicate daemons. This is a durable detached session, not a reboot service: after container restart, reopen the workspace or explicitly start it. Persistent tools survive only when placed on persistent storage.

Default saved-edit debounce is 3 seconds; remote poll is 30 seconds plus request duration, with network error backoff. These are not promises of measured latency. Changing them requires checking the stability probe's freshness threshold (65 seconds) and actual network latency. Keep the conservative defaults initially.

## 4. GUI and hooks acceptance

Use the title-bar cloud button or status-bar “保存并同步”; the settings/status menu exposes sync, check, pause, resume, and conflict actions. No command-palette-only workflow is required. Every connected window protects unsaved buffers; the initiating window need not be the only window.

Merge `hooks.fragment.json` into the client's existing hook configuration, preserving all other hooks. Trust the actual hooks in the client and verify an audit entry. See [codex-and-wake.md](codex-and-wake.md), then run [verification.md](verification.md). Do not claim the hook is active merely because a file exists.

## References

- [Overleaf Git authentication](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/git-integration/git-integration-authentication-tokens)
- [Overleaf Git operations](https://docs.overleaf.com/integrations-and-add-ons/git-integration-and-github-synchronization/git-integration/advanced-git-operations)
- [Codex skill authoring](https://learn.chatgpt.com/docs/build-skills)
