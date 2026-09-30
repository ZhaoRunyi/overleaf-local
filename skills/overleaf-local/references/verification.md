# Verification and acceptance

## Automated, isolated checks

Run `python scripts/regression.py /path/to/generated/deployment` on a disposable generated deployment. It imports that engine and uses local bare Git remotes and an editor adapter in `/tmp`, not Overleaf or the user's paper. It exercises save/push, fetch/apply, nonoverlap merge, conflict retention/confirmation, dirty buffers, missing editor, save and push races, allowlists, offline recovery, binary conflicts, and deletion safety. This is not actual GUI or Internet acceptance.

Run `python3 scripts/regression_guards.py /path/to/generated/deployment` for multi-window veto, stale conflict refresh and quiet-readiness tests. Run `node scripts/regression_ui.js /path/to/generated/deployment PROJECT_ID` for native merge command arguments, draft reuse, guarded whole-file choices and confirmed submission with a mocked VS Code UI. Unix sockets and Node subprocesses may require the host rather than a restricted sandbox. Missing host permissions are not test failures in synchronization logic, but the test remains unexecuted until rerun with those capabilities.

Validate the skill with the installed skill-creator `quick_validate.py`. Compile Python and parse JS in a temporary cache without creating caches inside the skill. Generate two deployments and compare project IDs, namespaces and config paths, not file hashes. No credentials or live project IDs may be present in the reusable package.

## Real project acceptance (authorized changes only)

1. Check noninteractive Git authentication and record request latency without printing credentials.
2. Open two windows for the same project. With both clean, test update; with one dirty, ensure remote application waits and a visible reminder appears. Close/reconnect a window and verify no stale ownership blocks sync.
3. Add an agreed harmless comment locally, save, verify its exact content on Overleaf; change it on Overleaf and verify local content. Delete the test comment through the same normal flow with authorization.
4. Make independent-line edits on both sides and confirm both survive. Deliberately conflict on one harmless test line, accept one hunk, save the draft, submit, then confirm the pause clears. Repeat with a remote change after opening a draft; stale submission must not overwrite it.
5. Invoke Codex read/edit tools and verify actual hook audit. Change remote source after read; the stale patch should be blocked. Do not perform ten real edits to a user's manuscript merely to test the retry counter; use a disposable project.
6. Where requested, arm a quiet watcher on an authorized unfinished test task and verify the same thread receives the continuation. Fake probe output alone does not test delivery.
7. In Overleaf History, find the agreed local edit amid web edits and inspect a prior version. This validates the actual UI behavior for that account, not a universal per-commit history guarantee.

## PDF verification

Git does not contain the PDF produced by the Overleaf compiler. Ask for a downloaded PDF from the same source revision and the site's compiler/TeX Live version. Match main document, fonts, packages, shell-escape needs, and bibliography engine before compiling locally. Never change an official conference style to force a comparison.

Use the Python runtime created by `scripts/bootstrap_runtime.sh` with
`scripts/compare_pdfs.py LOCAL.pdf OVERLEAF.pdf --out /tmp/pdf-comparison.json`. Poppler's
`pdftotext` and `pdftoppm` must also be available. The comparison checks page count, page sizes and
word coordinates, then page pixels at 180 and 300 DPI. Exact checks compare files' rendered
content, not metadata-dependent PDF bytes. Different creation timestamps do not imply a visible
difference. Matching finite-resolution renders are strong rendering checks but not a mathematical
identity proof for every possible renderer.

If only sources match, report only source parity. If words match but pixels differ, inspect fonts/images/rasterization. If a source changed while the user downloaded the PDF, repeat against a known revision instead of declaring compiler failure. Delete user-supplied PDFs afterward only when explicitly requested.

## Provenance and delivery

Runtime derived from the working paper-sync deployment (extension 0.1.6), generalized into per-project paths and namespaces. Its earlier live-project verification does not automatically validate a newly generated deployment, a different client version, or a new account. Deliver an acceptance checklist naming passed automated tests and the real UI/network checks still required.
