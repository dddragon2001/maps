#!/usr/bin/env python3
"""Two-way git sync for the Maps folder (standard library only).

Run every 5 minutes by Task Scheduler, once per account that holds a copy:
  1. commit any local changes
  2. pull from GitHub, replaying local commits on top (rebase)
  3. push anything GitHub does not have yet
Every run appends one line to logs/sync.log (logs/ is not synced).
On a conflict it aborts the rebase, logs CONFLICT and exits 1, leaving
your files as they were so you can fix it by hand.

Usage:  python sync_maps.py
"""
import datetime
import os
import socket
import subprocess
import sys

REMOTE, BRANCH = "origin", "main"
ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "logs", "sync.log")


def git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                           text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 127, "git not found on PATH"
    return p.returncode, (p.stdout + p.stderr).strip()


def log(status, detail=""):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    who = "%s/%s" % (socket.gethostname(), os.environ.get("USERNAME", os.environ.get("USER", "?")))
    line = "%s %s %s %s" % (stamp, who, status, " ".join(detail.split())[:300])
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")
    print(line)


def main():
    if os.path.isdir(os.path.join(ROOT, ".git", "rebase-merge")) or \
       os.path.isdir(os.path.join(ROOT, ".git", "rebase-apply")) or \
       os.path.exists(os.path.join(ROOT, ".git", "MERGE_HEAD")):
        log("BLOCKED", "a rebase or merge is already in progress; finish or abort it by hand")
        return 1

    git("add", "-A")
    committed = git("diff", "--cached", "--quiet")[0] != 0
    if committed:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        code, out = git("commit", "-m", "auto-sync %s %s" % (os.environ.get("USERNAME", "?"), stamp))
        if code:
            log("ERROR", "commit failed: " + out)
            return 1

    code, out = git("pull", "--rebase", REMOTE, BRANCH)
    if code:
        git("rebase", "--abort")
        log("CONFLICT" if "CONFLICT" in out else "ERROR", "pull failed: " + out)
        return 1

    ahead = git("rev-list", "--count", "%s/%s..HEAD" % (REMOTE, BRANCH))[1]
    if ahead.isdigit() and int(ahead) > 0:
        code, out = git("push", REMOTE, "HEAD:" + BRANCH)
        if code:
            log("ERROR", "push failed: " + out)
            return 1
        log("OK", "pushed %s commit(s)" % ahead)
    else:
        log("OK", "committed, nothing new to push" if committed else "up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
