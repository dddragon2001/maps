#!/usr/bin/env python3
"""MAPS routine runner (standard library only).

Fired every 5 minutes by Task Scheduler as claude-agent. Each run:
  1. git pull, so routines.json, prompts and todo.md are current
  2. finds routines in routines.json that are due on this machine
  3. checks the two caps against logs/runs.log (daily, rolling window)
  4. runs each due routine with `claude -p` (limited tools, turns, timeout)
  5. sends the result itself (Telegram), so Claude never needs a send tool
  6. appends one line per run to logs/runs.log:
       time  name  model  turns  cost_usd  status
logs/ is not synced. Telegram settings come from the user environment
variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.

Usage:  python run_routines.py               run whatever is due
        python run_routines.py --run NAME    run NAME now (caps still apply)
        python run_routines.py --print NAME  run NAME now, print, do not send
"""
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(ROOT, "routines.json")
LOG_DIR = os.path.join(ROOT, "logs")
RUNS_LOG = os.path.join(LOG_DIR, "runs.log")
STATE = os.path.join(LOG_DIR, "routines_state.json")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def now():
    return datetime.datetime.now()


def machine():
    return "%s/%s" % (socket.gethostname(), os.environ.get("USERNAME", os.environ.get("USER", "?")))


def run(cmd, timeout=120, stdin=None):
    try:
        p = subprocess.run(cmd, cwd=ROOT, input=stdin, capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 127, "%s not found" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def log_run(name, model, turns, cost, status):
    os.makedirs(LOG_DIR, exist_ok=True)
    fields = [now().isoformat(timespec="seconds"), name, model, str(turns), "%.4f" % cost,
              " ".join(status.split())[:200]]
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write("\t".join(fields) + "\n")
    print("\t".join(fields))


def past_runs():
    """(time, name, status) for every real run in the log; CAPPED lines are not runs."""
    out = []
    if not os.path.exists(RUNS_LOG):
        return out
    with open(RUNS_LOG, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            try:
                t = datetime.datetime.fromisoformat(parts[0])
            except ValueError:
                continue
            out.append((t, parts[1], parts[5]))
    return out


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_state(state):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)


def is_due(r, last, t):
    """Schedules: 'daily HH:MM' or 'every N min'. last is an ISO time or None."""
    kind, _, arg = r.get("schedule", "").partition(" ")
    last_t = datetime.datetime.fromisoformat(last) if last else None
    if kind == "daily":
        hh, mm = (int(x) for x in arg.split(":"))
        slot = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return t >= slot and (last_t is None or last_t < slot)
    if kind == "every":
        minutes = int(arg.split()[0])
        return last_t is None or t - last_t >= datetime.timedelta(minutes=minutes)
    raise ValueError("unknown schedule %r" % r.get("schedule"))


def cap_reason(caps, t):
    runs = [x for x in past_runs() if not x[2].startswith("CAPPED")]
    today = sum(1 for x in runs if x[0].date() == t.date())
    if today >= caps.get("max_runs_per_day", 12):
        return "CAPPED daily limit %d reached" % caps.get("max_runs_per_day", 12)
    window = datetime.timedelta(minutes=caps.get("window_minutes", 60))
    recent = sum(1 for x in runs if t - x[0] < window)
    if recent >= caps.get("max_runs_per_window", 3):
        return "CAPPED %d runs in the last %d min" % (recent, caps.get("window_minutes", 60))
    return None


def context_block(r, t):
    parts = ["Now: %s (%s)" % (t.strftime("%Y-%m-%d %H:%M"), t.strftime("%A"))]
    for item in r.get("context", []):
        if item == "todo":
            path = os.path.join(ROOT, "todo.md")
            text = open(path, encoding="utf-8").read() if os.path.exists(path) else "(todo.md missing)"
            parts.append("=== todo.md ===\n" + text)
        elif item == "git_24h":
            code, out = run(["git", "log", "--since=24 hours ago", "--name-only",
                             "--pretty=format:-- %ad %s", "--date=format:%Y-%m-%d %H:%M"])
            parts.append("=== git log, last 24 hours ===\n" + (out.strip() or "no commits"))
        elif item == "runs_tail":
            lines = []
            if os.path.exists(RUNS_LOG):
                with open(RUNS_LOG, encoding="utf-8") as f:
                    lines = f.read().splitlines()[-20:]
            parts.append("=== run log, last 20 lines (time name model turns cost status) ===\n"
                         + ("\n".join(lines) or "empty"))
    return "\n\n".join(parts)


def find_claude():
    found = shutil.which("claude")
    if found:
        return found
    for p in (os.path.expanduser(r"~\.local\bin\claude.exe"),
              os.path.expanduser(r"~\AppData\Roaming\npm\claude.cmd")):
        if os.path.exists(p):
            return p
    return "claude"


def run_claude(r, t):
    """Returns (text, turns, cost, status)."""
    prompt_path = os.path.join(ROOT, r["prompt"])
    with open(prompt_path, encoding="utf-8") as f:
        prompt = f.read()
    stdin = prompt + "\n\n" + context_block(r, t)
    cmd = [find_claude(), "-p", "--output-format", "json",
           "--model", r.get("model", "sonnet"),
           "--max-turns", str(r.get("max_turns", 4)),
           "--allowedTools", ",".join(r.get("allowed_tools", [])) or "Read"]
    if r.get("effort"):
        cmd += ["--settings", json.dumps({"effortLevel": r["effort"]})]
    code, out = run(cmd, timeout=r.get("timeout_seconds", 300), stdin=stdin)
    if code in (124, 127):
        return "", 0, 0.0, "ERROR " + out
    start = out.find("{")
    try:
        data = json.loads(out[start:]) if start >= 0 else {}
    except ValueError:
        data = {}
    if not data:
        return "", 0, 0.0, "ERROR exit %d: %s" % (code, out.strip()[:150])
    turns, cost = data.get("num_turns", 0), float(data.get("total_cost_usd", 0) or 0)
    if data.get("is_error") or data.get("subtype") != "success":
        return "", turns, cost, "ERROR %s %s" % (data.get("subtype", "?"), str(data.get("result", ""))[:120])
    return data.get("result", "").strip(), turns, cost, "OK"


def user_env(name):
    """Process environment first, then the user's saved variables (HKCU\\Environment).
    A window opened with Start-Process -Credential inherits the caller's environment,
    so the saved ones are read straight from the registry."""
    value = os.environ.get(name, "")
    if value or os.name != "nt":
        return value
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return ""


def send_telegram(text):
    token = user_env("TELEGRAM_BOT_TOKEN")
    chat = user_env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set for this user"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    try:
        with urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token, body, timeout=30) as resp:
            ok = json.loads(resp.read().decode()).get("ok")
        return None if ok else "Telegram said not ok"
    except Exception as e:  # the token is in the URL, so never log str(e) from urllib verbatim
        return "Telegram send failed: %s" % type(e).__name__


def do_routine(r, caps, state, t, send=True):
    name, model = r["name"], r.get("model", "sonnet")
    reason = cap_reason(caps, t)
    if reason:
        if state.get(name + ".capped") != t.date().isoformat():
            log_run(name, model, 0, 0.0, reason)
            state[name + ".capped"] = t.date().isoformat()
        return
    text, turns, cost, status = run_claude(r, t)
    state[name] = t.isoformat(timespec="seconds")  # mark the slot used even on error, so it is not retried every 5 min
    if status == "OK":
        if not send or r.get("output") != "telegram":
            print(text)
        else:
            err = send_telegram("MAPS %s\n\n%s" % (name, text))
            if err:
                status = "SEND_FAILED " + err
    elif send and r.get("output") == "telegram":
        send_telegram("MAPS %s did not run: %s. See logs\\runs.log." % (name, status[:200]))
    log_run(name, model, turns, cost, status)


def main(argv):
    t = now()
    code, out = run(["git", "pull", "--ff-only", "origin", "main"])
    if code:
        print("git pull failed, using the files as they are: " + out.strip()[:200])
    reg = load_json(REGISTRY, None)
    if not reg:
        log_run("runner", "-", 0, 0.0, "ERROR routines.json missing or not valid JSON")
        return 1
    state = load_json(STATE, {})
    caps = reg.get("caps", {})
    forced = argv[1] if len(argv) > 1 and argv[0] in ("--run", "--print") else None
    for r in reg.get("routines", []):
        if forced:
            if r["name"] == forced:
                do_routine(r, caps, state, t, send=argv[0] == "--run")
            continue
        if not r.get("enabled", True) or r.get("machine", "").lower() != machine().lower():
            continue
        try:
            due = is_due(r, state.get(r["name"]), t)
        except ValueError as e:
            log_run(r["name"], r.get("model", "-"), 0, 0.0, "ERROR " + str(e))
            continue
        if due:
            do_routine(r, caps, state, t)
    save_state(state)
    try:
        write_routines_panel(reg)
    except Exception as e:  # the dashboard must never break a run
        print("panel not written: %s" % e)
    return 0


def write_routines_panel(reg):
    """Dashboard panel: each routine's settings and last run, today's cap use, recent runs."""
    from panels import write_panel
    t = now()
    lines = []
    if os.path.exists(RUNS_LOG):
        with open(RUNS_LOG, encoding="utf-8") as f:
            lines = [l.rstrip("\n").split("\t") for l in f if l.count("\t") >= 5]
    runs = [x for x in past_runs() if not x[2].startswith("CAPPED")]
    caps = reg.get("caps", {})
    window = datetime.timedelta(minutes=caps.get("window_minutes", 60))
    rows = []
    for r in reg.get("routines", []):
        last = [l for l in lines if l[1] == r["name"]]
        rows.append({"name": r["name"], "enabled": r.get("enabled", True), "schedule": r.get("schedule"),
                     "machine": r.get("machine"), "model": r.get("model"), "output": r.get("output"),
                     "last_time": last[-1][0] if last else None,
                     "last_status": last[-1][5] if last else "never run"})
    cost_today = sum(float(l[4]) for l in lines if l[0][:10] == t.date().isoformat() and l[4].replace(".", "", 1).isdigit())
    write_panel("routines", rows,
                caps={"runs_today": sum(1 for x in runs if x[0].date() == t.date()),
                      "max_runs_per_day": caps.get("max_runs_per_day", 12),
                      "runs_in_window": sum(1 for x in runs if t - x[0] < window),
                      "max_runs_per_window": caps.get("max_runs_per_window", 3),
                      "window_minutes": caps.get("window_minutes", 60)},
                cost_today_usd=round(cost_today, 4),
                recent=[{"time": l[0], "name": l[1], "model": l[2], "turns": l[3], "cost": l[4], "status": l[5]}
                        for l in lines[-15:]][::-1],
                runs=[{"time": l[0], "name": l[1], "model": l[2], "turns": l[3], "cost": l[4], "status": l[5]}
                      for l in lines[-300:]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
