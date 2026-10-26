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


def write_panels():
    """Dashboard panels: recent sync results, and open items from todo.md."""
    from panels import write_panel
    import re
    sync = []
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as f:
            for line in f.read().splitlines()[-10:]:
                parts = line.split(" ", 3)
                if len(parts) >= 3:
                    sync.append({"time": parts[0], "who": parts[1], "status": parts[2],
                                 "detail": parts[3] if len(parts) > 3 else ""})
    write_panel("sync", sync[::-1])

    todo = os.path.join(ROOT, "todo.md")
    if not os.path.exists(todo):
        return
    today = datetime.date.today()
    section, rows = "", []
    with open(todo, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if section == "Open" and line.startswith("- [ ]"):
                text = line[5:].strip()
                m = re.search(r"due:(\d{4}-\d{2}-\d{2})", text)
                due = m.group(1) if m else None
                days = (datetime.date.fromisoformat(due) - today).days if due else None
                rows.append({"kind": "open", "text": re.sub(r"\s*due:\S+", "", text), "due": due,
                             "days_left": days})
            elif section == "Waiting" and line.startswith("- "):
                rows.append({"kind": "waiting", "text": line[2:].strip(), "due": None, "days_left": None})
    rows.sort(key=lambda r: (r["kind"] != "open", r["days_left"] is None, r["days_left"] or 0))
    write_panel("todo", rows)

    import build_brain
    build_brain.main()


if __name__ == "__main__":
    code = main()
    try:
        write_panels()
    except Exception as e:  # the dashboard must never break a sync
        print("panels not written: %s" % e)
    sys.exit(code)
