from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from solar_platform.services.data_pull import JuggleDataPullService


MONTH_FOLDER_RE = re.compile(r"^\d{4}\s\d{2}$")


@dataclass
class FileImportResult:
    csv_path: Path
    plant_alias: str | None
    plant_uid: str | None
    rows_in_csv: int
    rows_imported: int
    interval_minutes: float | None
    conversion_factor: float | None
    status: str
    detail: str = ""


def _norm_name(value: str) -> str:
    text = value.lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = text.replace("&", " and ")
    text = text.replace("'", "")
    text = re.sub(r"\s+", " ", text)
    return text


def _best_match(name: str, aliases: list[str], threshold: float = 0.56) -> str | None:
    nn = _norm_name(name)
    best_alias = None
    best_score = 0.0
    for alias in aliases:
        score = SequenceMatcher(None, nn, _norm_name(alias)).ratio()
        if score > best_score:
            best_score = score
            best_alias = alias
    if best_alias and best_score >= threshold:
        return best_alias
    return None


def _find_time_col(columns: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for key in ["time", "date & time", "timestamp", "datetime", "date"]:
        if key in lower:
            return lower[key]
    return None


def _find_gti_col(columns: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for key in ["gti", "poa", "poa_irradiance", "irradiance", "ghi"]:
        if key in lower:
            return lower[key]
    return None


def _interval_minutes(ts: pd.Series) -> float | None:
    if ts.empty:
        return None
    diffs = ts.sort_values().diff().dropna().dt.total_seconds() / 60.0
    if diffs.empty:
        return None
    return float(diffs.median())


def _to_30m_wm2(df: pd.DataFrame, time_col: str, gti_col: str) -> tuple[pd.DataFrame, float | None, float | None]:
    out = df[[time_col, gti_col]].copy()
    out[time_col] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    out[gti_col] = pd.to_numeric(out[gti_col], errors="coerce")
    out = out.dropna(subset=[time_col, gti_col])
    if out.empty:
        return pd.DataFrame(columns=["ts", "poa_wm2"]), None, None

    out["ts"] = out[time_col].dt.floor("min")
    interval = _interval_minutes(out["ts"]) or 15.0

    # Inputs are interval energy (kWh/m² per interval); aggregate to 30-min energy.
    by_ts = out.groupby("ts", as_index=True)[gti_col].mean().sort_index()
    gti_30m = by_ts.resample("30min").sum(min_count=1).dropna()

    # Convert 30-min kWh/m² to W/m²: (kWh/m² / 0.5h) * 1000 = *2000
    factor = 2000.0
    poa_wm2 = gti_30m * factor

    result = pd.DataFrame({"ts": poa_wm2.index, "poa_wm2": poa_wm2.values})
    result = result[result["poa_wm2"] >= 0]
    result["ts"] = result["ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return result, interval, factor


def main() -> int:
    parser = argparse.ArgumentParser(description="Import irradiance CSVs from repo into DuckDB readings as POA payloads")
    parser.add_argument("--root", type=Path, default=Path("tools/irradiation-data"), help="Folder containing month subfolders")
    parser.add_argument("--dry-run", action="store_true", help="Parse/validate only, do not write to DB")
    parser.add_argument("--match-threshold", type=float, default=0.56, help="Fuzzy match threshold for plant alias")
    parser.add_argument("--limit-files", type=int, default=0, help="Optional cap on number of CSV files processed")
    args = parser.parse_args()

    root = args.root
    if not root.exists():
        raise SystemExit(f"Data root not found: {root}")

    svc = JuggleDataPullService()
    plants = svc.get_registered_plants()
    alias_to_uid = {p["alias"]: p["plant_uid"] for p in plants}
    aliases = list(alias_to_uid.keys())

    csv_files: list[Path] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or not MONTH_FOLDER_RE.match(sub.name):
            continue
        csv_files.extend(sorted(sub.glob("*.csv")))

    if args.limit_files > 0:
        csv_files = csv_files[: args.limit_files]

    results: list[FileImportResult] = []
    grouped_readings: dict[str, list[dict]] = {}

    for csv_path in csv_files:
        file_alias = csv_path.stem
        matched_alias = _best_match(file_alias, aliases, threshold=args.match_threshold)
        if not matched_alias:
            results.append(FileImportResult(csv_path, None, None, 0, 0, None, None, "unmatched", "no plant alias match"))
            continue

        plant_uid = alias_to_uid[matched_alias]

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            results.append(FileImportResult(csv_path, matched_alias, plant_uid, 0, 0, None, None, "error", f"read_csv failed: {exc}"))
            continue

        time_col = _find_time_col(df.columns.tolist())
        gti_col = _find_gti_col(df.columns.tolist())
        if not time_col or not gti_col:
            results.append(
                FileImportResult(
                    csv_path,
                    matched_alias,
                    plant_uid,
                    len(df),
                    0,
                    None,
                    None,
                    "skipped",
                    f"missing cols time={time_col} gti={gti_col}",
                )
            )
            continue

        converted, interval, factor = _to_30m_wm2(df, time_col, gti_col)
        if converted.empty:
            results.append(FileImportResult(csv_path, matched_alias, plant_uid, len(df), 0, interval, factor, "skipped", "no valid rows after parsing"))
            continue

        # sanity checks
        p99 = float(converted["poa_wm2"].quantile(0.99))
        if p99 > 1600:
            results.append(FileImportResult(csv_path, matched_alias, plant_uid, len(df), 0, interval, factor, "skipped", f"implausible p99={p99:.1f} W/m²"))
            continue

        emig_id = f"POA:SOLARGIS:{re.sub(r'[^A-Z0-9]+', '_', matched_alias.upper()).strip('_')}"
        readings = [
            {
                "ts": row.ts,
                "emigId": emig_id,
                "poaIrradiance": {"value": float(row.poa_wm2), "unit": "W/m2"},
                "source": "SolarGIS",
            }
            for row in converted.itertuples(index=False)
        ]

        grouped_readings.setdefault(plant_uid, []).extend(readings)
        results.append(FileImportResult(csv_path, matched_alias, plant_uid, len(df), len(readings), interval, factor, "prepared"))

    written = 0
    if not args.dry_run:
        for plant_uid, readings in grouped_readings.items():
            written += svc._store_readings(plant_uid, readings)

    # report
    matched = sum(1 for r in results if r.status in {"prepared", "skipped", "error"} and r.plant_alias)
    unmatched = sum(1 for r in results if r.status == "unmatched")
    prepared_rows = sum(r.rows_imported for r in results if r.status == "prepared")

    print("IRRADIANCE_IMPORT_SUMMARY")
    print(json.dumps({
        "files_seen": len(csv_files),
        "files_matched": matched,
        "files_unmatched": unmatched,
        "rows_prepared": prepared_rows,
        "rows_written": written,
        "dry_run": args.dry_run,
    }, indent=2))

    report_path = Path("platform/reports/tmp/irradiance_import_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            [
                {
                    "csv": str(r.csv_path),
                    "plant_alias": r.plant_alias,
                    "plant_uid": r.plant_uid,
                    "rows_in_csv": r.rows_in_csv,
                    "rows_imported": r.rows_imported,
                    "interval_minutes": r.interval_minutes,
                    "conversion_factor": r.conversion_factor,
                    "status": r.status,
                    "detail": r.detail,
                }
                for r in results
            ],
            indent=2,
        )
    )
    print(f"REPORT: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
