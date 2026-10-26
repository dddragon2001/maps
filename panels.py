"""Writes dashboard panel files (standard library only).

Each producer calls write_panel() with what it already knows; the dashboard
only reads these files. Panels go to DATA_DIR, a folder outside the repo that
both accounts can write: C:\\MAPS\\screen\\data unless MAPS_SCREEN_DATA says
otherwise. If the folder does not exist, nothing is written and nothing fails.
"""
import datetime
import json
import os

DATA_DIR = os.environ.get("MAPS_SCREEN_DATA", r"C:\MAPS\screen\data")


def write_panel(name, rows, stale_minutes=15, **extra):
    """Replace DATA_DIR/<name>.json in one step. Returns the path, or None."""
    if not os.path.isdir(DATA_DIR):
        return None
    doc = {"panel": name,
           "generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "stale_minutes": stale_minutes,
           "rows": rows}
    doc.update(extra)
    path = os.path.join(DATA_DIR, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path
