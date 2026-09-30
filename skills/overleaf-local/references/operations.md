# Day-to-day operations and recovery

## Expected behavior

| Event | Behavior |
|---|---|
| Local saved allowed-file edit | Debounce, fetch, reconcile, ordinary commit and non-forced push |
| Unsaved local buffer | Never upload the unsaved text; defer remote writes and notify |
| Overleaf change | Poll, trial merge, validate all connected editors, apply through an editor, update Git |
| Different-line changes | Three-way merge if Git can reconcile them; retain both contributions |
| Same-line overlap | Preserve both revisions, pause, open merge UI; no automatic winner |
| Multiple windows | Check every window; any dirty/busy/stale buffer blocks application |
| Missing editor | Defer remote application; reconnect the protected extension |
| Network failure | Keep local edits, back off, report failure, resume when reachable |
| Remote edit during push | Refuse overwrite, fetch again, merge or pause |
| New/deleted/unapproved file | Require explicit allowlist/repository review; do not silently publish |
| Codex stale read | Block the patch, synchronize, reread, reconstruct; bounded retry/wake |

Unsaved-buffer notifications are reminders, not permission to discard input. Never delete a socket merely because a PID appears old: query it, verify ownership, and distinguish a dead connection from a live dirty window. UI status is from a prior fetch, not an assertion of continuously synchronized servers.

## Resolve conflicts graphically

1. Click “冲突：选择本地 / Overleaf” or the conflict entry in the sync menu.
2. Choose the native three-way merge view for selective changes, or explicitly choose the entire local/Overleaf file. Red/green panes are comparisons, not a completed resolution.
3. Work in the result/draft, not the manuscript source. Save it. After accepting one hunk, continue through remaining hunks; one acceptance does not mean the file is submitted.
4. Click “继续解决并提交冲突” / “提交合并结果” and review the confirmation. “保存并同步” also recognizes a pending draft and routes to submission.
5. Submission rechecks the local source and remote revision. If either changed, refresh and review again rather than applying the stale draft. On success, confirm a synchronized status and that both sides contain the result.

The UI reads recorded conflict snapshots locally for speed; it does not fetch merely to open each pane. Explicit refresh and final submission fetch. Native merge editor invocation uses VS Code's internal `_open.mergeEditor` command, so validate compatibility after a VS Code upgrade; a fallback diff alone does not provide the same acceptance UX. Binary conflicts require deliberate whole-file choice/replacement rather than textual merge.

## Manual inspection

```bash
python /path/to/deployment/sync.py status
python /path/to/deployment/sync.py check
python /path/to/deployment/sync.py inspect-conflict
python /path/to/deployment/sync.py pause
python /path/to/deployment/sync.py resume
```

`check` fetches; `status` reads service status. Prefer UI conflict submission over manually deleting the pause file. The CLI's reviewed-resolution path requires explicit acceptance; never invoke it on behalf of an undecided user. Before changing allowlists or replacing a figure binary, pause and inspect both revisions. Keep conflict drafts until confirmed published, then remove disposable drafts.

## History and latency limitations

Ordinary Git push preserves shared source history and avoids destructive rewrites. Do not promise that each local commit appears as one independently labeled Overleaf History entry or preserves web comments/Track Changes. Validate the user's actual History UI with a harmless agreed change. Overleaf PDF compilation is separate; Auto Compile and TeX settings are controlled on the website.

Measure local-save→remote visibility, web-edit→local visibility, no-change fetch duration, and conflict-view opening separately. Poll frequency is not transfer duration. Do not promise instantaneous or keystroke-level synchronization. Report network conditions and observed range, not just an optimistic minimum.

## Rollback tools, not manuscripts

Pause the service and disable this project's extension/hooks to stop automation; retain both manuscript revisions and credential configuration. Restore a previous tool package only after checking schema compatibility. Never roll back manuscript text as a side effect of a tool upgrade. A live deployment is not automatically migrated when a newer skill package is installed.
