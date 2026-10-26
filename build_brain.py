#!/usr/bin/env python3
"""Builds the dashboard's brain graph (standard library only).

Walks the map from Card 1: the master signpost, each area signpost, every
file or folder they link to, and a few files inside each linked folder.
Routines come from routines.json; runs come from the routines panel that
the runner writes. Output: brain.json in the panel folder, as
  nodes: [{id, kind, label, area, layer, path, note, changed, deg}]
  links: [{s, t}]
Run by sync_maps.py after each sync. Reads only; writes only brain.json.

Usage:  python build_brain.py
"""
import datetime
import json
import os
import re

from check_signposts import HEADING, MASTER, ROOT, is_url, links, read, resolve
from panels import DATA_DIR, write_panel

MAX_FILES_PER_FOLDER = 40   # files listed inside each linked folder
MAX_DEPTH = 2               # how deep to look inside a linked folder
MAX_RUNS = 300              # newest runs drawn
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "logs"}

SECTION_KIND = {"Projects": "project", "State": "memory", "Skills": "skill", "Memory": "memory",
                "Routines": "routine", "Not here": "app",
                "Maintenance": "app", "Pulse": "routine", "Screen": "app"}
KIND_LAYER = {"root": "core", "area": "core", "project": "apps", "app": "apps", "skill": "skills",
              "memory": "memory", "note": "memory", "routine": "routines", "run": "runs"}
LINE = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*:?\s*(.*)$")


def mtime(path):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    except OSError:
        return None


class Graph:
    def __init__(self):
        self.nodes, self.links, self.ids = [], [], set()

    def node(self, nid, kind, label, area, path="", note="", changed=None):
        if nid not in self.ids:
            self.ids.add(nid)
            self.nodes.append({"id": nid, "kind": kind, "label": label, "area": area,
                               "layer": KIND_LAYER[kind], "path": path, "note": note,
                               "changed": changed or (mtime(path) if path and not is_url(path) else None)})
        return nid

    def link(self, s, t):
        if s != t:
            self.links.append({"s": s, "t": t})


def entries(lines):
    """(section, label, target, note) for every bulleted link in a signpost."""
    section = ""
    for line in lines:
        h = HEADING.match(line)
        if h:
            section = h.group(1)
            continue
        m = LINE.match(line)
        if m:
            yield section, m.group(1), m.group(2).strip(), m.group(3).strip()


def add_folder(g, parent, folder, area):
    """A few files inside a linked folder, newest first, as note nodes."""
    found = []
    base_depth = folder.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if dirpath.count(os.sep) - base_depth >= MAX_DEPTH:
            dirnames[:] = []
        for name in filenames:
            if not name.startswith("."):
                p = os.path.join(dirpath, name)
                found.append((os.path.getmtime(p) if os.path.exists(p) else 0, p))
    for _, p in sorted(found, reverse=True)[:MAX_FILES_PER_FOLDER]:
        g.link(parent, g.node("f:" + p, "note", os.path.relpath(p, folder), area, p))


def build():
    g = Graph()
    master_path = os.path.join(ROOT, MASTER)
    root = g.node("root", "root", "signpost.md", "system", master_path, "Master signpost, hop 1 of 2")
    for section, label, target, note in entries(read(master_path)):
        path = resolve(target, ROOT)
        if os.path.basename(path).lower() == MASTER and os.path.isfile(path):
            area = os.path.basename(os.path.dirname(path))
            a = g.node("a:" + area, "area", label, area, path, note)
            g.link(root, a)
            for sec, lab, tgt, nt in entries(read(path)):
                kind = SECTION_KIND.get(sec, "note")
                p = tgt if is_url(tgt) else resolve(tgt, os.path.dirname(path))
                n = g.node("n:" + p, kind, lab, area, p, nt)
                g.link(a, n)
                if not is_url(p) and os.path.isdir(p):
                    add_folder(g, n, p, area)
        else:
            n = g.node("n:" + path, SECTION_KIND.get(section, "app"), label, "system", path, note)
            g.link(root, n)

    reg = {}
    try:
        with open(os.path.join(ROOT, "routines.json"), encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError):
        pass
    for r in reg.get("routines", []):
        rid = g.node("r:" + r["name"], "routine", r["name"], "system", "",
                     "%s on %s, %s" % (r.get("schedule"), r.get("machine"), r.get("model")))
        g.link(root, rid)

    try:
        with open(os.path.join(DATA_DIR, "routines.json"), encoding="utf-8") as f:
            runs = json.load(f).get("runs", [])
    except (OSError, ValueError):
        runs = []
    for i, run in enumerate(runs[-MAX_RUNS:]):
        parent = "r:" + run.get("name", "?")
        if parent not in g.ids:
            g.node(parent, "routine", run.get("name", "?"), "system")
            g.link(root, parent)
        g.link(parent, g.node("run:%d:%s" % (i, run.get("time")), "run", run.get("status", ""), "system",
                              "", "%s, %s turns, $%s" % (run.get("model"), run.get("turns"), run.get("cost")),
                              run.get("time")))

    deg = {}
    for l in g.links:
        deg[l["s"]] = deg.get(l["s"], 0) + 1
        deg[l["t"]] = deg.get(l["t"], 0) + 1
    for n in g.nodes:
        n["deg"] = deg.get(n["id"], 0)
    return g


def main():
    g = build()
    path = write_panel("brain", g.nodes, stale_minutes=24 * 60, links=g.links,
                       counts={"files": sum(1 for n in g.nodes if n["kind"] not in ("run", "area", "root")),
                               "links": len(g.links),
                               "runs": sum(1 for n in g.nodes if n["kind"] == "run")})
    print("brain: %d nodes, %d links -> %s" % (len(g.nodes), len(g.links), path or "panel folder missing"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
