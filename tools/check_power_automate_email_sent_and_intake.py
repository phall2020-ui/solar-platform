#!/usr/bin/env python3
"""
Health-checks for the two Power Automate flows:
- AI Intake (Keyword Trigger)
- AI Sent Items -> Notion

Usage:
  FLOW_ACCESS_TOKEN=... python check_power_automate_email_sent_and_intake.py
  FLOW_ACCESS_TOKEN=... python check_power_automate_email_sent_and_intake.py --trigger
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

API = "2016-11-01"
ENV_ID = "Default-8b064fff-a093-43f9-ab3f-504161bc844b"


@dataclass(frozen=True)
class FlowSpec:
    key: str
    flow_id: str
    display_name: str
    required_actions: List[str]


FLOWS = [
    FlowSpec(
        key="intake",
        flow_id="a3c88904-435c-4998-b832-f1e2c8fb7bdc",
        display_name="AI Intake (Keyword Trigger)",
        required_actions=["Get_emails_(V3)", "Get_emails_Archive_(V3)", "Apply_to_each"],
    ),
    FlowSpec(
        key="sent",
        flow_id="d68b1662-c62d-4018-8a90-adf5cad14128",
        display_name="AI Sent Items -> Notion",
        required_actions=["Get_emails_(V3)", "Apply_to_each", "HTTP_Check_Existing", "HTTP"],
    ),
]


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def flow_base(flow_id: str) -> str:
    return f"https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV_ID}/flows/{flow_id}"


def trigger_url(flow_id: str) -> str:
    return (
        f"https://unitedkingdom.api.flow.microsoft.com:443/providers/Microsoft.ProcessSimple/environments/"
        f"{ENV_ID}/flows/{flow_id}/triggers/Recurrence/run?api-version={API}"
    )


def get_json(url: str, token: str) -> Dict[str, Any]:
    r = requests.get(url, headers=auth_header(token), timeout=60)
    r.raise_for_status()
    return r.json()


def post(url: str, token: str) -> int:
    r = requests.post(url, headers=auth_header(token), timeout=60)
    return r.status_code


def latest_run(token: str, flow_id: str) -> Optional[Dict[str, Any]]:
    j = get_json(f"{flow_base(flow_id)}/runs?api-version={API}&%24top=1", token)
    vals = j.get("value", [])
    return vals[0] if vals else None


def wait_for_new_run(token: str, flow_id: str, previous_name: Optional[str], timeout_sec: int = 180) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        run = latest_run(token, flow_id)
        if run and run.get("name") != previous_name:
            status = ((run.get("properties") or {}).get("status")) or ""
            if status in {"Succeeded", "Failed", "Cancelled"}:
                return run
        time.sleep(2)
    return None


def collect_action_names(actions: Dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for name, action in (actions or {}).items():
        names.add(name)
        nested = action.get("actions")
        if isinstance(nested, dict):
            names.update(collect_action_names(nested))
        else_branch = (action.get("else") or {}).get("actions")
        if isinstance(else_branch, dict):
            names.update(collect_action_names(else_branch))
        for case in (action.get("cases") or {}).values():
            case_actions = (case or {}).get("actions")
            if isinstance(case_actions, dict):
                names.update(collect_action_names(case_actions))
        default_actions = (action.get("default") or {}).get("actions")
        if isinstance(default_actions, dict):
            names.update(collect_action_names(default_actions))
    return names


def check_flow(token: str, spec: FlowSpec, run_now: bool) -> Dict[str, Any]:
    flow = get_json(f"{flow_base(spec.flow_id)}?api-version={API}", token)
    props = flow.get("properties", {})
    definition = props.get("definition", {})
    actions = (definition.get("actions") or {})
    all_action_names = collect_action_names(actions)
    trigger_interval = (
        (definition.get("triggers") or {})
        .get("Recurrence", {})
        .get("recurrence", {})
        .get("interval")
    )
    missing = [a for a in spec.required_actions if a not in all_action_names]
    latest = latest_run(token, spec.flow_id)
    latest_status = ((latest or {}).get("properties") or {}).get("status")

    out: Dict[str, Any] = {
        "flow_id": spec.flow_id,
        "name": props.get("displayName", spec.display_name),
        "state": props.get("state"),
        "trigger_interval_minutes": trigger_interval,
        "missing_actions": missing,
        "latest_run_status": latest_status,
        "latest_run_name": (latest or {}).get("name"),
        "trigger_result": None,
    }

    if run_now:
        previous = (latest or {}).get("name")
        code = post(trigger_url(spec.flow_id), token)
        run = wait_for_new_run(token, spec.flow_id, previous)
        out["trigger_result"] = {
            "http_status": code,
            "new_run_name": (run or {}).get("name"),
            "new_run_status": ((run or {}).get("properties") or {}).get("status"),
            "timed_out": run is None,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", action="store_true", help="Trigger each flow once and wait for completion.")
    args = parser.parse_args()

    token = os.environ.get("FLOW_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("FLOW_ACCESS_TOKEN is required")

    result = {"ok": True, "flows": []}
    for spec in FLOWS:
        flow_result = check_flow(token, spec, run_now=args.trigger)
        result["flows"].append(flow_result)
        if flow_result["state"] != "Started":
            result["ok"] = False
        if flow_result["missing_actions"]:
            result["ok"] = False
        if args.trigger and (flow_result["trigger_result"] or {}).get("new_run_status") != "Succeeded":
            result["ok"] = False

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
