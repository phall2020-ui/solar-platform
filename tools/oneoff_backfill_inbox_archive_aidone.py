#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

ENV_ID = "Default-8b064fff-a093-43f9-ab3f-504161bc844b"
FLOW_ID = "a3c88904-435c-4998-b832-f1e2c8fb7bdc"
BASE = f"https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV_ID}/flows/{FLOW_ID}"
API = "2016-11-01"
TRIGGER_URL = (
    f"https://unitedkingdom.api.flow.microsoft.com:443/providers/Microsoft.ProcessSimple/environments/"
    f"{ENV_ID}/flows/{FLOW_ID}/triggers/Recurrence/run?api-version={API}"
)
STATE_PATH = "/tmp/oneoff_threefolder_state.json"

ACTIONS = {
    "inbox": "Get_emails_(V3)",
    "archive": "Get_emails_Archive_(V3)",
    "aidone": "Get_emails_AIDone_(V3)",
}
EXCLUDE_QUERY = "-from:PowerAutomateNoReply@microsoft.com"
DONE_QUERY = "received<=1900-01-01"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_to_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def minus_one_sec(iso_str: str) -> str:
    return to_iso(iso_to_dt(iso_str) - timedelta(seconds=1))


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    now = utcnow()
    target = now - timedelta(days=14)
    state = {
        "target_start": to_iso(target),
        "top": 5,
        "exclude_query": EXCLUDE_QUERY,
        "folders": {
            "inbox": {"cutoff": to_iso(now), "done": False},
            "archive": {"cutoff": to_iso(now), "done": False},
            "aidone": {"cutoff": to_iso(now), "done": False},
        },
        "iterations": 0,
        "logs": [],
    }
    save_state(state)
    return state


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_json(url: str, token: str) -> Dict[str, Any]:
    r = requests.get(url, headers=auth_header(token), timeout=60)
    r.raise_for_status()
    return r.json()


def patch_json(url: str, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.patch(
        url,
        headers={**auth_header(token), "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def post_trigger(token: str) -> int:
    r = requests.post(TRIGGER_URL, headers=auth_header(token), timeout=60)
    return r.status_code


def latest_run(token: str) -> Optional[Dict[str, Any]]:
    runs_url = f"{BASE}/runs?api-version={API}&%24top=1"
    j = get_json(runs_url, token)
    vals = j.get("value", [])
    return vals[0] if vals else None


def wait_for_new_run(token: str, previous_name: Optional[str], timeout_sec: int = 900) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = latest_run(token)
        if r and r.get("name") != previous_name:
            status = (((r.get("properties") or {}).get("status")) or "")
            if status in {"Succeeded", "Failed", "Cancelled"}:
                return r
        time.sleep(2)
    return None


def get_actions(token: str, run_name: str) -> Dict[str, Any]:
    u = f"{BASE}/runs/{run_name}/actions?api-version={API}&%24top=200"
    j = get_json(u, token)
    by = {}
    for a in j.get("value", []):
        by[a.get("name")] = a
    return by


def action_stats(action: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not action:
        return {"status": "Missing", "error": "missing action", "count": 0, "min": None, "max": None}
    props = action.get("properties") or {}
    out = {
        "status": props.get("status"),
        "error": ((props.get("error") or {}).get("message", "")),
        "count": 0,
        "min": None,
        "max": None,
    }
    link = (props.get("outputsLink") or {}).get("uri")
    if not link:
        return out
    try:
        o = requests.get(link, timeout=60)
        o.raise_for_status()
        data = o.json()
        arr = (((data.get("body") or {}).get("value")) or [])
        out["count"] = len(arr)
        dates = sorted([m.get("receivedDateTime") for m in arr if m.get("receivedDateTime")])
        if dates:
            out["min"] = dates[0]
            out["max"] = dates[-1]
    except Exception as e:
        out["error"] = f"{out['error']} | outputs fetch failed: {e}".strip(" |")
    return out


def build_query(folder_state: Dict[str, Any], exclude_query: str) -> str:
    if folder_state.get("done"):
        return DONE_QUERY
    cutoff = str(folder_state.get("cutoff", "")).replace("Z", "")
    return f"received<={cutoff} AND {exclude_query}"


def all_done(state: Dict[str, Any]) -> bool:
    f = state["folders"]
    return f["inbox"]["done"] and f["archive"]["done"] and f["aidone"]["done"]


def resolve_actions(def_actions: Dict[str, Any]) -> Dict[str, Optional[str]]:
    # Some flow revisions do not include an explicit AI Done fetch action.
    return {
        "inbox": ACTIONS["inbox"] if ACTIONS["inbox"] in def_actions else None,
        "archive": ACTIONS["archive"] if ACTIONS["archive"] in def_actions else None,
        "aidone": ACTIONS["aidone"] if ACTIONS["aidone"] in def_actions else None,
    }


def main() -> None:
    token = os.environ.get("FLOW_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("FLOW_ACCESS_TOKEN is required")

    max_iter = int(os.environ.get("MAX_ITER", "200"))
    inter_sleep = int(os.environ.get("INTER_RUN_SLEEP_SEC", "20"))

    state = load_state()
    target = iso_to_dt(state["target_start"])

    print(f"Target start: {state['target_start']}")
    print(f"Initial top: {state['top']}")

    for _ in range(max_iter):
        if all_done(state):
            print("Backfill complete for all folders.")
            break

        flow_url = f"{BASE}?api-version={API}"
        flow = get_json(flow_url, token)
        actions = flow["properties"]["definition"]["actions"]
        resolved = resolve_actions(actions)

        # Keep low-rate schedule and bounded fetch
        trig = flow["properties"]["definition"]["triggers"]["Recurrence"]
        trig["recurrence"]["interval"] = 10
        trig["evaluatedRecurrence"]["interval"] = 10

        q_in = build_query(state["folders"]["inbox"], state["exclude_query"])
        q_ar = build_query(state["folders"]["archive"], state["exclude_query"])
        q_ai = build_query(state["folders"]["aidone"], state["exclude_query"])

        for folder_key, query in (("inbox", q_in), ("archive", q_ar), ("aidone", q_ai)):
            action_name = resolved[folder_key]
            if not action_name:
                state["folders"][folder_key]["done"] = True
                continue
            actions[action_name]["inputs"]["queries"]["top"] = state["top"]
            actions[action_name]["inputs"]["queries"]["searchQuery"] = query

        patch_json(flow_url, token, flow)

        prev = latest_run(token)
        prev_name = prev.get("name") if prev else None

        trig_code = post_trigger(token)
        run = wait_for_new_run(token, prev_name, timeout_sec=900)
        if not run:
            print("Timeout waiting for run completion")
            break

        run_name = run.get("name")
        run_status = ((run.get("properties") or {}).get("status"))
        by_name = get_actions(token, run_name)

        st_in = action_stats(by_name.get(resolved["inbox"])) if resolved["inbox"] else {"status": "Skipped", "error": "", "count": 0, "min": None, "max": None}
        st_ar = action_stats(by_name.get(resolved["archive"])) if resolved["archive"] else {"status": "Skipped", "error": "", "count": 0, "min": None, "max": None}
        st_ai = action_stats(by_name.get(resolved["aidone"])) if resolved["aidone"] else {"status": "Skipped", "error": "", "count": 0, "min": None, "max": None}

        loop_err = (((by_name.get("Apply_to_each") or {}).get("properties") or {}).get("error") or {}).get("message", "")
        errs = f"{st_in['error']} {st_ar['error']} {st_ai['error']} {loop_err}".lower()
        throttled = "thrott" in errs

        for k, stx in (("inbox", st_in), ("archive", st_ar), ("aidone", st_ai)):
            fstate = state["folders"][k]
            if fstate["done"]:
                continue
            if stx["count"] == 0:
                fstate["done"] = True
            elif stx["min"] and iso_to_dt(stx["min"]) <= target:
                fstate["done"] = True
            elif stx["min"]:
                fstate["cutoff"] = minus_one_sec(stx["min"])

        if throttled:
            state["top"] = max(3, int(state["top"]) - 1)

        state["iterations"] += 1
        row = {
            "t": to_iso(utcnow()),
            "run": run_name,
            "run_status": run_status,
            "trigger_http": trig_code,
            "throttled": throttled,
            "top": state["top"],
            "queries": {"inbox": q_in, "archive": q_ar, "aidone": q_ai},
            "stats": {"inbox": st_in, "archive": st_ar, "aidone": st_ai},
            "folders": json.loads(json.dumps(state["folders"])),
        }
        state["logs"].append(row)
        save_state(state)

        print(json.dumps({
            "iter": state["iterations"],
            "run": run_name,
            "status": run_status,
            "throttled": throttled,
            "top": state["top"],
            "inbox": st_in,
            "archive": st_ar,
            "aidone": st_ai,
            "done": state["folders"],
        }, indent=2))

        if all_done(state):
            print("Backfill complete for all folders.")
            break

        time.sleep(inter_sleep)

    # Restore steady scheduled queries to exclude flow-alert sender only.
    try:
        flow_url = f"{BASE}?api-version={API}"
        flow = get_json(flow_url, token)
        actions = flow["properties"]["definition"]["actions"]
        resolved = resolve_actions(actions)
        trig = flow["properties"]["definition"]["triggers"]["Recurrence"]
        trig["recurrence"]["interval"] = 10
        trig["evaluatedRecurrence"]["interval"] = 10
        for nm in (resolved["inbox"], resolved["archive"], resolved["aidone"]):
            if not nm:
                continue
            actions[nm]["inputs"]["queries"]["searchQuery"] = EXCLUDE_QUERY
            actions[nm]["inputs"]["queries"]["top"] = 10
        patch_json(flow_url, token, flow)
        print("Restored scheduled intake query defaults.")
    except Exception as e:
        print(f"WARN: failed restoring defaults: {e}")

    # Print terminal summary
    st = load_state()
    summary = {
        "target_start": st["target_start"],
        "iterations": st["iterations"],
        "top": st["top"],
        "folders": st["folders"],
        "all_done": all_done(st),
        "throttled_runs": sum(1 for x in st.get("logs", []) if x.get("throttled")),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
