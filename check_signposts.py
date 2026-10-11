#!/usr/bin/env python3
"""Nightly MAPS signpost checker (standard library only).

Checks:
  1. Master signpost is under 60 lines; area signposts are under 80 lines.
  2. Every area signpost has the six sections, in order:
     Projects, State, Skills, Memory, Routines, Not here.
  3. Every local path linked from any signpost exists (URLs are skipped).
  4. Two-hop rule: master links go only to area signposts (or files in the
     root); area links never point at another signpost.
  5. One home per fact: no local target is linked from more than one place.
  6. No unreferenced folders: every area folder is in the master, every
     folder directly inside an area is linked from that area's signpost, and
     every project folder in PROJECTS_ROOT is linked from some area signpost.

Exits 0 when everything passes, 1 when any check fails.
Usage:  python check_signposts.py
"""
import os
import re
import sys

# Absolute paths in the signposts are written against this root. They are
# mapped onto the folder this script lives in, so the check still works if the
# folder is moved, renamed in case, or mounted somewhere else.
MAPS_ROOT = r"F:\Cloude_Code\maps"
ROOT = os.path.dirname(os.path.abspath(__file__))
# Your project folders live next to maps\ and are mapped the same way.
PROJECTS_ROOT = r"F:\Cloude_Code"
PROJECTS_DIR = os.path.dirname(ROOT)
# Folders in PROJECTS_ROOT that are not projects and need no signpost entry.
NOT_PROJECTS = {"maps", "cowork"}

MASTER = "signpost.md"
SECTIONS = ["Projects", "State", "Skills", "Memory", "Routines", "Not here"]
MASTER_MAX, AREA_MAX = 60, 80
IGNORED_DIRS = {".git", "__pycache__", ".claude", ".vscode", "logs"}

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^##\s+(.+?)\s*$")

errors = []


def fail(msg):
    errors.append(msg)


def is_url(target):
    return re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) is not None


def resolve(target, base_dir):
    """Turn a link target into a real path on this machine."""
    t = target.strip().replace("\\", "/")
    for alias, real in ((MAPS_ROOT, ROOT), (PROJECTS_ROOT, PROJECTS_DIR)):
        a = alias.replace("\\", "/").rstrip("/")
        if t.lower() == a.lower() or t.lower().startswith(a.lower() + "/"):
            return os.path.normpath(os.path.join(real, t[len(a):].lstrip("/")))
    if os.path.isabs(t) or re.match(r"^[A-Za-z]:/", t):
        return os.path.normpath(t)
    return os.path.normpath(os.path.join(base_dir, t))


def links(lines):
    for n, line in enumerate(lines, 1):
        for m in LINK.finditer(line):
            yield n, m.group(1)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(path, folder):
    p = os.path.normcase(os.path.abspath(path))
    f = os.path.normcase(os.path.abspath(folder))
    return p == f or p.startswith(f + os.sep)


def main():
    master_path = os.path.join(ROOT, MASTER)
    if not os.path.isfile(master_path):
        print("FAIL master signpost missing: " + master_path)
        return 1

    homes = {}  # normalized target -> "file:line" of first link
    master = read(master_path)
    if len(master) >= MASTER_MAX:
        fail("%s: %d lines (limit is under %d)" % (MASTER, len(master), MASTER_MAX))

    areas = []  # area signpost paths found via the master
    all_linked = []  # every local target linked from an area signpost
    for n, target in links(master):
        where = "%s:%d" % (MASTER, n)
        if is_url(target):
            continue
        path = resolve(target, ROOT)
        key = os.path.normcase(path)
        if key in homes:
            fail("%s: %s is already linked at %s (one home per fact)" % (where, target, homes[key]))
        homes[key] = where
        if not os.path.exists(path):
            fail("%s: missing path %s" % (where, target))
            continue
        if os.path.basename(path).lower() == MASTER:
            areas.append(path)
        elif not same(os.path.dirname(path), ROOT):
            fail("%s: master must link to area signposts, not %s (two-hop rule)" % (where, target))

    for sp in areas:
        area_dir = os.path.dirname(sp)
        rel = os.path.relpath(sp, ROOT)
        lines = read(sp)
        if len(lines) >= AREA_MAX:
            fail("%s: %d lines (limit is under %d)" % (rel, len(lines), AREA_MAX))

        found = [m.group(1) for m in map(HEADING.match, lines) if m]
        if found != SECTIONS:
            fail("%s: sections are %s, expected %s" % (rel, found, SECTIONS))

        linked = []
        for n, target in links(lines):
            where = "%s:%d" % (rel, n)
            if is_url(target):
                continue
            path = resolve(target, area_dir)
            key = os.path.normcase(path)
            if key in homes:
                fail("%s: %s is already linked at %s (one home per fact)" % (where, target, homes[key]))
            homes[key] = where
            if not os.path.exists(path):
                fail("%s: missing path %s" % (where, target))
            if os.path.basename(path).lower() == MASTER:
                fail("%s: area signposts must not link to another signpost (two-hop rule)" % where)
            linked.append(path)
            all_linked.append(path)

        for name in sorted(os.listdir(area_dir)):
            sub = os.path.join(area_dir, name)
            if not os.path.isdir(sub) or name in IGNORED_DIRS or name.startswith("."):
                continue
            if not any(inside(p, sub) for p in linked):
                fail("%s: folder %s is not referenced in its signpost" % (rel, os.path.relpath(sub, ROOT)))

    area_dirs = [os.path.dirname(a) for a in areas]
    for name in sorted(os.listdir(ROOT)):
        sub = os.path.join(ROOT, name)
        if not os.path.isdir(sub) or name in IGNORED_DIRS or name.startswith("."):
            continue
        if not any(same(sub, d) for d in area_dirs):
            fail("%s: folder %s is not referenced in the master signpost" % (MASTER, name))

    for name in sorted(os.listdir(PROJECTS_DIR)):
        sub = os.path.join(PROJECTS_DIR, name)
        if not os.path.isdir(sub) or name.startswith(".") or name.lower() in NOT_PROJECTS:
            continue
        if not any(inside(p, sub) for p in all_linked):
            fail("project folder %s\\%s is not linked from any area signpost" % (PROJECTS_ROOT, name))

    if errors:
        for e in errors:
            print("FAIL " + e)
        print("%d problem(s) found across %d signposts." % (len(errors), len(areas) + 1))
        return 1
    print("OK: %d signposts, %d local links, all checks passed." % (len(areas) + 1, len(homes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
