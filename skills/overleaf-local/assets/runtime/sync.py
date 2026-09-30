#!/usr/bin/env python3
"""One serialized Git synchronizer; editor-mediated remote writes, no force push."""
import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import tempfile
import threading
import time

HOME = Path(__file__).resolve().parent


def rpc(path, payload, timeout=90):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(json.dumps(payload).encode() + b"\n")
        response = connection.makefile("rb").readline(32 * 1024 * 1024)
    if not response:
        raise RuntimeError("Connection closed without a response")
    return json.loads(response)


class Paused(Exception):
    pass


class Synchronizer:
    def __init__(self, config):
        self.config = config
        self.repo = Path(config["repo"])
        self.runtime = Path(config["runtime"])
        self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.allowed = set(config["files"])
        self.remote = config["remote"]
        self.branch = config["branch"]
        self.remote_ref = f"refs/remotes/{self.remote}/{self.branch}"
        self.pause_file = self.repo / ".git/overleaf-local-paused"
        self.lock = threading.Lock()
        self.last_fetch = 0
        self.remote_head = None
        self.remote_stable_since = 0
        self.status = {"state": "starting", "message": "Not checked yet", "checked_at": None}

    def git(self, *args, repo=None, check=True):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=self.config["git_config"], GIT_TERMINAL_PROMPT="0")
        env.pop("GIT_ASKPASS", None)
        env.pop("SSH_ASKPASS", None)
        result = subprocess.run(["git", "-C", str(repo or self.repo), *args],
                                env=env, capture_output=True, timeout=40)
        if check and result.returncode:
            # Do not echo transport stderr, URLs, credentials, or manuscript contents.
            raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode}); check network/authentication or repository state")
        return result

    def text(self, *args, **kwargs):
        return self.git(*args, **kwargs).stdout.decode().strip()

    def report(self, state, message, **details):
        self.status = {"state": state, "message": message, "checked_at": self.last_fetch or None,
                       "updated_at": time.time(), **details}
        path = self.runtime / "status.json"
        temporary = path.with_suffix(".new")
        temporary.write_text(json.dumps(self.status, indent=2) + "\n")
        temporary.replace(path)
        return self.status

    def validate(self, ref):
        listing = self.git("ls-tree", "-rz", ref).stdout
        for row in listing.split(b"\0"):
            if not row:
                continue
            metadata, path = row.split(b"\t", 1)
            if path.decode() not in self.allowed or metadata.split()[0] not in (b"100644", b"100755"):
                raise Paused("Unapproved tracked file or symlink; review the upload allowlist")

    def snapshot(self):
        result = {}
        for name in sorted(self.allowed):
            path = self.repo / name
            if path.is_symlink() or not path.resolve().is_relative_to(self.repo.resolve()):
                raise Paused("Symlinks are not supported")
            result[name] = path.read_bytes() if path.exists() else None
        return result

    def editors(self):
        result = []
        for path in sorted(self.runtime.glob("editor-*.sock")):
            try:
                state = rpc(path, {"op": "status"}, timeout=3)
            except (OSError, ValueError, RuntimeError):
                continue
            if state.get("repo") == str(self.repo):
                result.append((path, state))
        return result

    def clean_editors(self, required=False):
        editors = self.editors()
        if any(state.get("dirty") for _, state in editors):
            raise Paused("Unsaved paper edits in VS Code; save them before synchronizing")
        if any(state.get("busy") for _, state in editors):
            raise Paused("An editor update is in progress; retry shortly")
        if required and not editors:
            raise Paused("Remote update waits for a connected Paper Sync editor")
        return sorted(editors, key=lambda item: not item[1].get("focused", False))

    def fetch(self):
        self.git("fetch", "--quiet", self.remote)
        self.validate(self.remote_ref)
        now = time.time()
        head = self.text("rev-parse", self.remote_ref)
        if head != self.remote_head or now - self.last_fetch > 65:
            self.remote_stable_since = now
        self.remote_head = head
        self.last_fetch = now

    def quiet(self):
        """Read-only local probe; the daemon already polls Overleaf."""
        with self.lock:
            try:
                self.clean_editors(required=True)
                if self.pause_file.exists() or self.dirty():
                    raise Paused("Paused or local changes pending")
                now = time.time()
                if now - self.last_fetch > 65 or any(self.divergence()):
                    raise Paused("Remote check stale or source synchronization pending")
                elapsed = now - self.remote_stable_since
                ready = elapsed >= 90 and self.status.get("state") == "synced"
                return {"ready": ready, "stable_seconds": int(elapsed),
                        "message": "Stable synchronized source" if ready else "Waiting for 90 seconds of observed stability"}
            except (Paused, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                return {"ready": False, "message": str(error)}

    def dirty(self):
        return bool(self.git("status", "--porcelain", "--untracked-files=no").stdout)

    def divergence(self):
        return [int(x) for x in self.text("rev-list", "--left-right", "--count", f"HEAD...{self.remote_ref}").split()]

    def check(self, pre_edit=False):
        with self.lock:
            try:
                self.validate("HEAD")
                self.fetch()
                ahead, behind = self.divergence()
                dirty = self.dirty()
                editors = self.clean_editors(required=pre_edit)
                if self.pause_file.exists():
                    raise Paused("Synchronization paused; resume or resolve the conflict first")
                if ahead or behind or dirty:
                    return self.report("pending", "Synchronize and reread the paper before editing",
                                       ahead=ahead, behind=behind, local_changes=dirty, allowed=False)
                return self.report("synced", "All tracked sources match the last remote fetch",
                                   head=self.text("rev-parse", "HEAD"), allowed=True, editors=len(editors))
            except Paused as error:
                return self.report("waiting", str(error), allowed=False)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                return self.report("error", str(error), allowed=False)

    def sync(self):
        with self.lock:
            try:
                if self.pause_file.exists():
                    if self.pause_file.read_text().lstrip().startswith("{"):
                        return self.report("conflict", "Conflicting edits retained; open the conflict view to review both versions")
                    return self.report("paused", "Paused; local and remote versions are retained")
                if self.text("branch", "--show-current") != self.branch:
                    raise Paused("Unexpected branch; automatic synchronization stopped")
                self.validate("HEAD")
                if self.git("ls-files", "-u").stdout:
                    raise Paused("An existing Git conflict needs manual resolution")
                staged_files = set(self.text("ls-files").splitlines())
                if not staged_files <= self.allowed:
                    raise Paused("Unapproved staged files; refuse to commit or upload")
                self.clean_editors()
                self.fetch()
                before = self.snapshot()
                if any(content is None for content in before.values()):
                    raise Paused("A required manuscript file is missing; review deletion before syncing")
                if self.dirty():
                    self.git("add", "-u", "--", *sorted(self.allowed))
                    self.git("commit", "--quiet", "-m", "Local manuscript edits")
                if self.snapshot() != before:
                    raise Paused("Files changed during commit; retry after saving finishes")
                head = self.text("rev-parse", "HEAD")
                ahead, behind = self.divergence()
                if behind:
                    self.clean_editors(required=True)
                    with tempfile.TemporaryDirectory(prefix="overleaf-local-merge-", dir="/tmp") as temporary:
                        trial = Path(temporary) / "repo"
                        self.git("clone", "--quiet", "--no-hardlinks", str(self.repo), str(trial))
                        self.git("config", "user.name", "Overleaf Local Sync", repo=trial)
                        self.git("config", "user.email", "paper-sync@localhost", repo=trial)
                        self.git("fetch", "--quiet", str(self.repo), self.remote_ref, repo=trial)
                        merge = self.git("merge", "--no-edit", "FETCH_HEAD", repo=trial, check=False)
                        if merge.returncode:
                            self.pause_file.write_text(json.dumps({"reason": "conflict", "local": head,
                                                                  "remote": self.text("rev-parse", self.remote_ref)}))
                            return self.report("conflict", "Conflicting edits; paper untouched by merge. Resolve both versions explicitly.",
                                               local=head, remote=self.text("rev-parse", self.remote_ref))
                        changes = []
                        for name, old in before.items():
                            target = trial / name
                            if not target.exists():
                                raise Paused("Remote deletion needs review")
                            new = target.read_bytes()
                            if old != new:
                                changes.append({"path": name, "before": base64.b64encode(old).decode(),
                                                "after": base64.b64encode(new).decode()})
                        if self.text("rev-parse", "HEAD") != head or self.snapshot() != before:
                            raise Paused("Local save raced with merge; retry with the latest files")
                        editors = self.clean_editors(required=True)
                        if changes:
                            for editor, state in editors:
                                if state.get("validate_updates"):
                                    response = rpc(editor, {"op": "check-update", "changes": changes}, timeout=10)
                                    if not response.get("ok"):
                                        raise Paused(response.get("error", "Another editor changed during merge"))
                            self.clean_editors(required=True)
                            response = rpc(editors[0][0], {"op": "apply", "changes": changes}, timeout=30)
                            if not response.get("ok"):
                                raise Paused(response.get("error", "Editor declined update"))
                            self.clean_editors(required=True)
                        expected = {name: (trial / name).read_bytes() for name in self.allowed}
                        if self.snapshot() != expected:
                            raise Paused("A new local edit was preserved; merge adoption waits for the next cycle")
                        self.git("fetch", "--quiet", str(trial), self.branch)
                        merged = self.text("rev-parse", "FETCH_HEAD")
                        # Update index/ref only: never reset or overwrite working files here.
                        self.git("read-tree", merged)
                        self.git("update-ref", f"refs/heads/{self.branch}", merged, head)
                if self.dirty():
                    raise Paused("New local changes detected; will process the next saved version")
                self.clean_editors()
                ahead, behind = self.divergence()
                if ahead:
                    push = self.git("push", "--quiet", self.remote, f"HEAD:refs/heads/{self.branch}", check=False)
                    if push.returncode:
                        return self.report("retry", "Push refused or connection failed; remote is never overwritten")
                self.fetch()
                ahead, behind = self.divergence()
                if ahead or behind or self.dirty():
                    return self.report("pending", "New edits arrived during synchronization; another cycle is needed")
                return self.report("synced", "All tracked sources match the last remote fetch", head=self.text("rev-parse", "HEAD"))
            except Paused as error:
                return self.report("waiting", str(error))
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                return self.report("error", str(error))

    def handle(self, request):
        operation = request.get("op")
        if operation == "quiet":
            return self.quiet()
        if operation == "editor-owner":
            return {"state": "ready", "message": "All connected windows can synchronize; choosing an owner is no longer needed"}
        if operation == "inspect-conflict":
            with self.lock:
                try:
                    conflict = json.loads(self.pause_file.read_text())
                    if conflict.get("reason") != "conflict":
                        raise Paused("No merge conflict to inspect")
                    if request.get("refresh"):
                        self.fetch()
                        conflict["remote"] = self.text("rev-parse", self.remote_ref)
                        self.pause_file.write_text(json.dumps(conflict))
                    base = self.text("merge-base", conflict["local"], conflict["remote"])
                    names = self.text("diff", "--name-only", base, conflict["remote"]).splitlines()
                    return {"state": "conflict", "message": "Review every incoming change before accepting the saved local resolution",
                            "base": base, **conflict, "files": names}
                except (Paused, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    return {"state": "waiting", "message": str(error)}
        if operation == "status":
            return self.status
        if operation == "check":
            return self.check()
        if operation == "pre-edit":
            return self.check(pre_edit=True)
        if operation == "sync":
            return self.sync()
        if operation == "resolve":
            with self.lock:
                if not request.get("accept_current_resolution"):
                    return self.report("waiting", "Explicit confirmation of the manually merged manuscript is required")
                try:
                    conflict = json.loads(self.pause_file.read_text())
                    self.fetch()
                    if request.get("reviewed_remote", conflict["remote"]) != conflict["remote"]:
                        raise Paused("Conflict snapshot changed in another window; reopen and review it")
                    if conflict.get("reason") != "conflict" or conflict["remote"] != self.text("rev-parse", self.remote_ref):
                        raise Paused("Remote changed since conflict review; inspect the new remote version first")
                    editors = self.clean_editors(required=True)
                    if not set(self.text("ls-files").splitlines()) <= self.allowed:
                        raise Paused("Unapproved staged files")
                    changes = request.get("changes", [])
                    if changes:
                        base = self.text("merge-base", conflict["local"], conflict["remote"])
                        incoming = set(self.text("diff", "--name-only", base, conflict["remote"]).splitlines())
                        if incoming != {change["path"] for change in changes}:
                            raise Paused("Review every incoming file before submitting the merge")
                        current = self.snapshot()
                        for change in changes:
                            if change["path"] not in self.allowed or current[change["path"]] != base64.b64decode(change["before"]):
                                raise Paused("Local source changed since review; reopen the conflict without overwriting it")
                            after = base64.b64decode(change["after"])
                            if b'<<<<<<< ' in after or b'>>>>>>> ' in after:
                                raise Paused("Conflict markers remain in the merge draft")
                        for editor, state in editors:
                            if state.get("validate_updates"):
                                result = rpc(editor, {"op": "check-update", "changes": changes})
                                if not result.get("ok"):
                                    raise Paused(result.get("error", "Another editor blocked the merge"))
                        result = rpc(editors[0][0], {"op": "apply", "changes": changes})
                        if not result.get("ok"):
                            raise Paused(result.get("error", "Editor blocked the merge"))
                        self.clean_editors(required=True)
                        current = self.snapshot()
                        if any(current[change["path"]] != base64.b64decode(change["after"]) for change in changes):
                            raise Paused("New local edits during resolution; review again")
                    if not set(self.text("ls-files").splitlines()) <= self.allowed:
                        raise Paused("Unapproved staged files")
                    contents = self.snapshot()
                    if any(content is None or b'<<<<<<< ' in content or b'>>>>>>> ' in content for content in contents.values()):
                        raise Paused("Missing files or conflict markers remain")
                    self.git("add", "-u", "--", *sorted(self.allowed))
                    parent = self.text("rev-parse", "HEAD")
                    tree = self.text("write-tree")
                    merged = self.text("commit-tree", tree, "-p", parent, "-p", conflict["remote"],
                                       "-m", "User-reviewed manuscript conflict resolution")
                    if self.snapshot() != contents:
                        raise Paused("New edits occurred during resolution; review again")
                    self.git("update-ref", f"refs/heads/{self.branch}", merged, parent)
                    self.pause_file.unlink()
                except (Paused, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                    return self.report("waiting", str(error))
            return self.sync()
        if operation in ("pause", "resume"):
            with self.lock:
                if self.pause_file.exists() and self.pause_file.read_text().lstrip().startswith("{"):
                    return self.report("conflict", "Resolve the saved conflict explicitly; pause/resume cannot discard it")
                if operation == "pause":
                    self.pause_file.write_text("manual\n")
                    return self.report("paused", "Paused by user")
                self.pause_file.unlink(missing_ok=True)
            return self.sync()
        return {"state": "error", "message": "Unknown operation"}

    def watch(self):
        last_snapshot = self.snapshot()
        changed_at = None
        next_poll = 0
        failures = 0
        while True:
            time.sleep(1)
            try:
                current = self.snapshot()
                now = time.monotonic()
                if current != last_snapshot:
                    changed_at = now
                    last_snapshot = current
                ready = changed_at is not None and now - changed_at >= self.config["debounce_seconds"]
                if ready or (now >= next_poll and changed_at is None):
                    result = self.sync()
                    failures = failures + 1 if result["state"] in ("error", "retry") else 0
                    next_poll = now + min(300, self.config["poll_seconds"] * 2 ** min(failures, 4))
                    changed_at = None
                    last_snapshot = self.snapshot()
            except Exception as error:
                self.report("error", f"Watcher paused this cycle: {type(error).__name__}")
                time.sleep(5)


def serve(config):
    synchronizer = Synchronizer(config)
    lock_file = (synchronizer.runtime / "daemon.lock").open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    path = synchronizer.runtime / "service.sock"
    path.unlink(missing_ok=True)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                request = json.loads(self.rfile.readline(32 * 1024 * 1024))
                response = synchronizer.handle(request)
            except Exception as error:
                response = {"state": "error", "message": type(error).__name__}
            self.wfile.write(json.dumps(response).encode() + b"\n")

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    with Server(str(path), Handler) as server:
        os.chmod(path, 0o600)
        threading.Thread(target=synchronizer.watch, daemon=True).start()
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["serve", "status", "check", "sync", "pre-edit", "pause", "resume", "resolve", "quiet", "inspect-conflict"])
    parser.add_argument("--accept-current-resolution", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Fetch the latest remote conflict snapshot")
    parser.add_argument("--config", type=Path, default=HOME / "config.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.operation == "serve":
        serve(config)
    else:
        try:
            response = rpc(Path(config["runtime"]) / "service.sock", {"op": args.operation,
                           "accept_current_resolution": args.accept_current_resolution, "refresh": args.refresh})
        except (OSError, RuntimeError) as error:
            response = {"state": "offline", "message": "Sync service unavailable", "allowed": False}
        print(json.dumps(response, ensure_ascii=False, indent=2))
        if args.operation == "pre-edit" and not response.get("allowed"):
            raise SystemExit(2)


if __name__ == "__main__":
    main()
