"""
Meter vs inverter comparison for solar sites.

Compares the grid-connection meter export reading against the inverter
generation figure for each site.  Both values come from the inverter
platform itself (Solis stationDetail API, SolarEdge monitoring API) — no
external metering provider required.

The comparison is run on the current-day totals available at the time of
the monitoring poll.  Results surface three kinds of issue:

  DISCREPANCY   — inverter and meter both have data but the loss factor
                  deviates from the expected site consumption by more than
                  discrepancy_threshold_pct (default 20%).

  INVERTER_ONLY — inverter shows generation but meter shows zero/None;
                  likely ELS export limitation or metering fault.

  METER_ONLY    — meter shows export but inverter shows zero/None;
                  likely an inverter monitoring gap.

  DATA_MISSING  — meter data not available for this site/platform;
                  logged but no ticket raised.

  OK            — within expected tolerance.

Config (config.yaml):

  meters:
    enabled: false
    discrepancy_threshold_pct: 20.0  # Flag if loss deviates > this % from expected
    min_generation_kwh: 5.0          # Skip comparison below this daily total
    # Per-site expected consumption (site load as % of inverter generation).
    # Defaults to 5.0 % if not specified.
    site_expected_loss:
      <site_id>: 7.0
"""

import logging
from typing import List, Optional

from .clients.base import (
    MeterComparisonResult,
    MeterComparisonStatus,
    SiteStatus,
)


class MeterChecker:
    """Compares inverter generation against meter export for all sites."""

    def __init__(self, config: dict):
        self.config = config.get('meters', {})
        self.enabled = self.config.get('enabled', False)
        self.threshold_pct = float(self.config.get('discrepancy_threshold_pct', 20.0))
        self.min_generation_kwh = float(self.config.get('min_generation_kwh', 5.0))
        self.site_expected_loss: dict = self.config.get('site_expected_loss', {})
        self.logger = logging.getLogger(__name__)

    def check_all(self, all_statuses: List[SiteStatus]) -> List[MeterComparisonResult]:
        """
        Run the meter vs inverter comparison for all sites.

        Returns one MeterComparisonResult per site that has meter data
        or is explicitly expected to have it.  Sites with no meter data
        at all (meter_export_kwh is None) still produce a DATA_MISSING
        result so they appear in the report.
        """
        results = []
        for status in all_statuses:
            if status.error_message:
                continue  # Skip sites that failed to poll
            result = self._compare(status)
            results.append(result)
        return results

    def _expected_loss(self, site_id: str) -> float:
        """Return the expected loss % for a site (site consumption + cable losses)."""
        return float(self.site_expected_loss.get(site_id, 5.0))

    def _compare(self, status: SiteStatus) -> MeterComparisonResult:
        inv_kwh = status.total_energy_today_kwh
        meter_kwh = status.meter_export_kwh

        # No meter data available for this platform/site
        if meter_kwh is None:
            return MeterComparisonResult(
                site_id=status.site_id,
                site_name=status.site_name,
                platform=status.platform,
                inverter_kwh=inv_kwh if inv_kwh else None,
                meter_export_kwh=None,
                loss_factor_pct=None,
                discrepancy_pct=None,
                status=MeterComparisonStatus.DATA_MISSING,
                detail="Meter data not available — check platform config.",
            )

        # Both values present — skip comparison on very low generation days
        if inv_kwh is not None and inv_kwh > 0 and meter_kwh is not None:
            if inv_kwh < self.min_generation_kwh and meter_kwh < self.min_generation_kwh:
                return MeterComparisonResult(
                    site_id=status.site_id,
                    site_name=status.site_name,
                    platform=status.platform,
                    inverter_kwh=inv_kwh,
                    meter_export_kwh=meter_kwh,
                    loss_factor_pct=None,
                    discrepancy_pct=None,
                    status=MeterComparisonStatus.OK,
                    detail=(
                        f"Low generation ({inv_kwh:.1f} kWh inverter, "
                        f"{meter_kwh:.1f} kWh meter) — comparison skipped."
                    ),
                )

        # Inverter shows generation, meter shows nothing
        if (inv_kwh or 0) > self.min_generation_kwh and (meter_kwh or 0) == 0:
            return MeterComparisonResult(
                site_id=status.site_id,
                site_name=status.site_name,
                platform=status.platform,
                inverter_kwh=inv_kwh,
                meter_export_kwh=meter_kwh,
                loss_factor_pct=None,
                discrepancy_pct=None,
                status=MeterComparisonStatus.INVERTER_ONLY,
                detail=(
                    f"Inverter shows {inv_kwh:.1f} kWh generated but meter reads "
                    f"{meter_kwh:.1f} kWh exported. Possible ELS curtailment or metering fault."
                ),
            )

        # Meter shows export, inverter shows nothing
        if (meter_kwh or 0) > self.min_generation_kwh and (inv_kwh or 0) == 0:
            return MeterComparisonResult(
                site_id=status.site_id,
                site_name=status.site_name,
                platform=status.platform,
                inverter_kwh=inv_kwh,
                meter_export_kwh=meter_kwh,
                loss_factor_pct=None,
                discrepancy_pct=None,
                status=MeterComparisonStatus.METER_ONLY,
                detail=(
                    f"Meter shows {meter_kwh:.1f} kWh exported but inverter reads zero. "
                    "Possible inverter monitoring gap."
                ),
            )

        # Both zero / both very low — treat as OK (e.g. night-time run)
        if (inv_kwh or 0) == 0 and (meter_kwh or 0) == 0:
            return MeterComparisonResult(
                site_id=status.site_id,
                site_name=status.site_name,
                platform=status.platform,
                inverter_kwh=inv_kwh,
                meter_export_kwh=meter_kwh,
                loss_factor_pct=None,
                discrepancy_pct=None,
                status=MeterComparisonStatus.OK,
                detail="Both inverter and meter read zero — likely night-time or pre-dawn poll.",
            )

        # Normal comparison: calculate loss factor
        loss_factor = ((inv_kwh - meter_kwh) / inv_kwh) * 100.0
        expected = self._expected_loss(status.site_id)
        discrepancy = abs(loss_factor - expected)

        if discrepancy > self.threshold_pct:
            comp_status = MeterComparisonStatus.DISCREPANCY
            detail = (
                f"Loss factor {loss_factor:.1f}% vs expected ~{expected:.0f}% "
                f"(deviation {discrepancy:.1f}%). "
                f"Inverter: {inv_kwh:.1f} kWh, meter: {meter_kwh:.1f} kWh."
            )
        else:
            comp_status = MeterComparisonStatus.OK
            detail = (
                f"Loss factor {loss_factor:.1f}% vs expected ~{expected:.0f}% — within tolerance. "
                f"Inverter: {inv_kwh:.1f} kWh, meter: {meter_kwh:.1f} kWh."
            )

        return MeterComparisonResult(
            site_id=status.site_id,
            site_name=status.site_name,
            platform=status.platform,
            inverter_kwh=inv_kwh,
            meter_export_kwh=meter_kwh,
            loss_factor_pct=round(loss_factor, 1),
            discrepancy_pct=round(discrepancy, 1),
            status=comp_status,
            detail=detail,
        )
