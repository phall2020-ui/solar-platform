from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "2026-02-20-Inverter-data-juggle-File-Notion-Sync-v01.py"
    spec = importlib.util.spec_from_file_location("notion_sync_v01", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import os

    cwd = os.getcwd()
    sys_path = list(sys.path)
    saved_modules = {name: sys.modules.get(name) for name in ("fetch_inverter_data", "solis_api", "solaredge_api")}
    try:
        os.chdir(script_path.parent)
        sys.path.insert(0, str(script_path.parent))
        fetch_mod = types.ModuleType("fetch_inverter_data")
        fetch_mod.BASE_URL = "https://example.invalid"
        fetch_mod.Config = object
        fetch_mod.fetch_all_readings = lambda *args, **kwargs: []
        solis_mod = types.ModuleType("solis_api")
        solis_mod.list_stations = lambda *args, **kwargs: {}
        solis_mod.get_station_month = lambda *args, **kwargs: {}
        solaredge_mod = types.ModuleType("solaredge_api")
        solaredge_mod.get_energy = lambda *args, **kwargs: {}
        sys.modules["fetch_inverter_data"] = fetch_mod
        sys.modules["solis_api"] = solis_mod
        sys.modules["solaredge_api"] = solaredge_mod
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        sys.path[:] = sys_path
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


def test_build_snapshot_details_includes_per_day_comparison_rows_with_solis_values() -> None:
    module = _load_module()

    details = module.build_snapshot_details(
        skipped_no_juggle_mapping=["Site A"],
        skipped_inverter_only=["Site B"],
        skipped_no_comparison_data=[],
        site_errors=["Site C error"],
        site_totals={
            "Finlay Beverages": {
                "platform": "solis",
                "inv_mtd": 320.0,
                "meter_mtd": 300.0,
                "platform_mtd": 310.0,
                "diff_mtd": 0.0667,
            }
        },
        comparison_rows=[
            {
                "site": "Finlay Beverages",
                "date": "2026-03-07",
                "platform": "solis",
                "juggle_inverter_kwh": 120.0,
                "juggle_meter_kwh": 118.0,
                "platform_kwh": 119.0,
                "solis_kwh": 119.0,
            }
        ],
    )

    assert details["skipped_no_juggle_mapping"] == ["Site A"]
    assert details["skipped_inverter_only"] == ["Site B"]
    assert details["site_errors"] == ["Site C error"]
    assert details["site_totals"]["Finlay Beverages"]["platform"] == "solis"
    assert details["comparison_rows"] == [
        {
            "site": "Finlay Beverages",
            "date": "2026-03-07",
            "platform": "solis",
            "juggle_inverter_kwh": 120.0,
            "juggle_meter_kwh": 118.0,
            "platform_kwh": 119.0,
            "solis_kwh": 119.0,
        }
    ]
