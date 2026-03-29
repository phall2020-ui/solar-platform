"""
solar-monitor — entry point for the inverter monitoring daemon.

Delegates to solar_platform.monitoring.daemon, which is the absorbed
Solar-Monitoring codebase.

Usage (after `pip install -e ".[monitoring]"`):
    solar-monitor                  # Run once and exit
    solar-monitor --schedule       # Run continuously (solar-aware, 2-hour intervals)
    solar-monitor --validate       # Validate config only
    solar-monitor --demo           # Run with demo data (no live API calls)
    solar-monitor --test-email     # Send test email and exit
    solar-monitor --test-ticket    # Send test O&M fault ticket and exit
    solar-monitor --seed-notion    # Pre-populate Notion from Asset Register

Config: solar-platform root directory must contain a config.yaml
(see Solar-Monitoring/config.yaml.example for the full schema).
"""

import sys


def main() -> None:
    """Entry point called by the solar-monitor console script."""
    # The daemon module uses argparse internally — delegate argv directly.
    # Import here (not at module level) so that importing cli.monitor
    # doesn't require monitoring deps to be installed.
    from solar_platform.monitoring import daemon
    daemon.main()


if __name__ == "__main__":
    main()
