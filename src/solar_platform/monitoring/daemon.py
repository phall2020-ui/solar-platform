#!/usr/bin/env python3
"""
Inverter Monitoring Script

Polls solar inverter platforms every N hours and generates status reports.
Supports: Solis, SolarEdge, Huawei FusionSolar, and Sungrow iSolarCloud.

Usage:
    python inverter_monitor.py                  # Run once and exit
    python inverter_monitor.py --schedule       # Run continuously with scheduler
    python inverter_monitor.py --validate       # Validate config only
    python inverter_monitor.py --demo           # Run with demo data
    python inverter_monitor.py --test-email     # Send a test email and exit
    python inverter_monitor.py --test-ticket    # Send a test fault ticket and exit
    python inverter_monitor.py --seed-notion    # Pre-populate Notion from Asset Register and exit
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yaml

try:
    import schedule
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

from .clients import (
    SolarEdgeClient,
    SolarEdgeBrowserClient,
    HuaweiClient,
    SolisClient,
    SungrowClient,
    SungrowWebClient,
    SungrowBrowserClient,
    SiteStatus,
    InverterStatus,
    InverterState,
)
from .clients.juggle import JuggleClient
from .clients.base import BaseInverterClient, MeterComparisonStatus
from .notifications import NotificationManager
from .ticket_generator import TicketGenerator
from .meter_checker import MeterChecker
from .notion_status_sync import NotionStatusSync

try:
    from astral import LocationInfo
    from astral.sun import sun
    HAS_ASTRAL = True
except ImportError:
    HAS_ASTRAL = False


# Configure logging
def setup_logging(log_to_file: bool = False, log_dir: str = "./logs"):
    """Configure logging to console and optionally to file."""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_to_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_file = Path(log_dir) / f"inverter_monitor_{datetime.now().strftime('%Y%m%d')}.log"
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers
    )
    return logging.getLogger(__name__)


def get_solar_schedule(logger: logging.Logger, date: Optional[datetime] = None) -> List[datetime]:
    """Calculate the solar-aware report schedule for the UK."""
    if not HAS_ASTRAL:
        logger.warning("Astral not installed. Cannot calculate solar schedule.")
        return []

    from datetime import timedelta
    if date is None:
        date = datetime.now(timezone.utc)
        
    try:
        # London coordinates
        city = LocationInfo("London", "UK", "Europe/London", 51.5074, -0.1278)
        s = sun(city.observer, date=date)
        
        sunrise = s['sunrise']
        sunset = s['sunset']
        
        first_run = sunrise + timedelta(hours=2)
        schedule_times = []
        
        current = first_run
        while current < sunset:
            schedule_times.append(current)
            current += timedelta(hours=2)
            
        # Ensure last report is at sunset
        schedule_times.append(sunset)
        
        return sorted(list(set(schedule_times)))
    except Exception as e:
        logger.error(f"Error calculating solar schedule for {date}: {e}")
        return []


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file and merge with environment variables."""
    path = Path(config_path)
    config = {}
    
    if path.exists():
        with open(path, 'r') as f:
            config = yaml.safe_load(f) or {}
    else:
        # Try to find config in script directory
        script_dir = Path(__file__).parent
        path = script_dir / config_path
        if path.exists():
            with open(path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            logging.warning(f"Configuration file not found: {config_path}. Using environment variables only.")

    # Override with environment variables: IM__SECTION__SUBSECTION__KEY
    # Example: IM__PLATFORMS__SOLAREDGE_BROWSER__USERNAME -> config['platforms']['solaredge_browser']['username']
    for env_key, env_val in os.environ.items():
        if env_key.startswith("IM__"):
            parts = env_key[4:].lower().split("__")
            
            # Navigate/build the nested dictionary
            current = config
            for i, part in enumerate(parts[:-1]):
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            
            # Set the value (convert "true"/"false" if appropriate)
            key = parts[-1]
            if env_val.lower() == "true":
                current[key] = True
            elif env_val.lower() == "false":
                current[key] = False
            else:
                current[key] = env_val
    
    return config


def get_enabled_clients(config: dict, logger: logging.Logger) -> List[BaseInverterClient]:
    """Initialize and return all enabled platform clients."""
    clients = []
    platforms = config.get('platforms', {})
    
    client_classes = {
        'solaredge': SolarEdgeClient,
        'solaredge_browser': SolarEdgeBrowserClient,
        'huawei': HuaweiClient,
        'solis': SolisClient,
        'sungrow': SungrowClient,
        'sungrow_web': SungrowWebClient,
        'sungrow_browser': SungrowBrowserClient,
        'juggle': JuggleClient,
    }
    
    for platform_name, platform_config in platforms.items():
        if not platform_config.get('enabled', False):
            continue
        
        client_class = client_classes.get(platform_name.lower())
        if not client_class:
            logger.warning(f"Unknown platform: {platform_name}")
            continue
        
        try:
            client = client_class(platform_config)
            is_valid, error = client.validate_config()
            if not is_valid:
                logger.warning(f"{platform_name}: {error}")
                continue
            clients.append(client)
            logger.info(f"Enabled client: {client.PLATFORM_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize {platform_name}: {e}")
    
    return clients


def calculate_pr(status: SiteStatus) -> Optional[float]:
    """
    Capacity utilisation (proxy for PR — actual irradiance not yet available).

    Returns capacity utilisation as a percentage (0–100), calculated as
    total_power_kw / installed_capacity_kw * 100.  Returns None when
    installed_capacity_kw is zero or unknown.
    """
    if status.installed_capacity_kw > 0:
        return (status.total_power_kw / status.installed_capacity_kw) * 100
    return None


def generate_report(all_statuses: List[SiteStatus], logger: logging.Logger, meter_results: Optional[list] = None) -> tuple[str, list, list]:
    """Generate a formatted "SOLAR FLEET DASHBOARD" status report."""
    now = datetime.now()
    lines = [
        "=" * 60,
        f"SOLAR FLEET DASHBOARD - {now.strftime('%Y-%m-%d %H:%M')}",
        "=" * 60,
        ""
    ]
    
    # Statistics calculations
    total_capacity_kw = 0.0
    total_power_kw = 0.0
    total_sites = 0
    online_sites = 0
    degraded_sites = 0
    offline_sites = 0
    
    comm_failures = []
    partial_outages = []
    
    # Helper to check for comm failure (>24h)
    def is_comm_failure(status: SiteStatus) -> tuple[bool, str]:
        if not status.last_data_time:
            return False, ""
        try:
            last_dt = None
            raw_val = status.last_data_time
            
            # Try parsing as UNIX timestamp (int or float)
            try:
                timestamp_val = float(raw_val)
                if timestamp_val > 1000000000000:
                    timestamp_val = timestamp_val / 1000
                last_dt = datetime.fromtimestamp(timestamp_val)
            except (ValueError, TypeError):
                pass
            
            # Try parsing as ISO format: "YYYY-MM-DD HH:MM"
            if last_dt is None:
                try:
                    last_dt = datetime.strptime(str(raw_val), '%Y-%m-%d %H:%M')
                except ValueError:
                    pass
            
            # Try parsing as time-only format: "HH:MM" (assume today)
            if last_dt is None:
                try:
                    time_part = datetime.strptime(str(raw_val), '%H:%M')
                    last_dt = now.replace(hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0)
                except ValueError:
                    pass
            
            if last_dt is None:
                return False, str(raw_val)
            
            delta = now - last_dt
            if delta.total_seconds() > 86400:  # 24 hours
                return True, last_dt.strftime('%Y-%m-%d %H:%M')
            return False, last_dt.strftime('%H:%M')
        except:
            return False, str(status.last_data_time)
    
    # Helper to determine if a site should be flagged as offline
    def should_flag_site_offline(status: SiteStatus, all_sites: List[SiteStatus]) -> bool:
        """
        Determine if a site should be flagged as offline based on context.
        
        CONSERVATIVE APPROACH: Only flag if we are CERTAIN the site should be online.
        - Explicit errors always flagged
        - Only flag if inverters have explicit OFFLINE state (not just WARNING or 0 power)
        - Require MAJORITY of peers to be generating significant power as confirmation
        """
        # If there's an explicit error message, flag it
        if status.error_message:
            return True
        
        # If no inverters at all, don't flag (we can't determine status)
        if status.inverter_count == 0:
            return False
        
        # If ANY inverters are online, site is not offline
        if status.online_count > 0:
            return False
        
        # Check if inverters have explicit OFFLINE state (not just WARNING or UNKNOWN)
        from clients.base import InverterState
        offline_inverters = sum(1 for inv in status.inverters if inv.state == InverterState.OFFLINE)
        
        # Only proceed if ALL inverters are explicitly OFFLINE
        if offline_inverters != status.inverter_count:
            return False  # Some are WARNING/UNKNOWN - not certain enough to flag
        
        # All inverters are explicitly OFFLINE - verify against peers
        # Require MAJORITY of peers generating SIGNIFICANT power (>1 kW) for confidence
        peer_sites = [s for s in all_sites 
                      if s.platform == status.platform 
                      and s.site_id != status.site_id
                      and s.inverter_count > 0]
        
        if len(peer_sites) >= 2:
            generating_peers = sum(1 for s in peer_sites if s.total_power_kw > 1.0)
            # Require at least 50% of peers generating significant power
            if generating_peers >= len(peer_sites) / 2:
                return True  # Majority of peers generating, this site isn't - high confidence
        
        # Not enough evidence to be certain - don't flag
        return False

    # Group by platform for detailed section
    platforms = {}
    
    for status in all_statuses:
        total_sites += 1
        total_capacity_kw += status.installed_capacity_kw
        total_power_kw += status.total_power_kw
        
        is_comm_fail, last_contact = is_comm_failure(status)
        
        # Categorize site status using smart detection
        if is_comm_fail:
            offline_sites += 1
            comm_failures.append((status, last_contact))
        elif should_flag_site_offline(status, all_statuses):
            offline_sites += 1
            comm_failures.append((status, last_contact))
        elif not status.is_fully_operational:
            degraded_sites += 1
            partial_outages.append(status)
        else:
            online_sites += 1
            
        platform = status.platform
        if platform not in platforms:
            platforms[platform] = []
        platforms[platform].append((status, last_contact))

    # FLEET SUMMARY
    lines.extend([
        "FLEET SUMMARY",
        "-" * 60,
        f"Total Capacity:  {total_capacity_kw/1000:.1f} MWp" if total_capacity_kw >= 1000 else f"Total Capacity:  {total_capacity_kw:.1f} kWp",
        f"Current Power:   {total_power_kw:.1f} kW",
        f"Sites Online:    {online_sites} / {total_sites}",
        f"Sites Degraded:  {degraded_sites}",
        f"Sites Offline:   {offline_sites}" + (" (No data > 24hrs)" if comm_failures else ""),
        ""
    ])
    
    # CRITICAL ALERTS
    if comm_failures or partial_outages:
        lines.extend([
            "CRITICAL ALERTS (Action Required)",
            "-" * 60
        ])
        
        if comm_failures:
            lines.append("🔴 COMMUNICATION FAILURES (>24h No Data)")
            for i, (status, last_contact) in enumerate(comm_failures, 1):
                lines.append(f"   {i}. {status.site_name} ({status.platform})")
                lines.append(f"      - Last Contact: {last_contact}")
                impact = f"{status.installed_capacity_kw:.1f} kWp Blind" if status.installed_capacity_kw > 0 else "Site Blind"
                lines.append(f"      - Impact: {impact}")
        
        if partial_outages:
            if comm_failures: lines.append("")
            lines.append("🟡 PARTIAL OUTAGES / WARNINGS")
            for i, status in enumerate(partial_outages, 1):
                lines.append(f"   {i}. {status.site_name} ({status.platform})")
                lines.append(f"      - Status: {status.online_count}/{status.inverter_count} Inverters Warning" if status.inverter_count > 0 else f"      - Status: {status.status_summary}")
                lines.append(f"      - Power: {status.total_power_kw:.1f} kW / {status.installed_capacity_kw:.1f} kWp")
        
        lines.append("")

    # DETAILED SITE STATUS
    lines.extend([
        "-" * 60,
        "DETAILED SITE STATUS (By Platform)",
        "-" * 60,
        ""
    ])
    
    for platform, items in platforms.items():
        # Check if all systems on this platform are normal
        all_normal = all(s.is_fully_operational and not is_comm_failure(s)[0] for s, _ in items)
        header_suffix = " (All Systems Normal)" if all_normal else " (Attention Required)"
        
        lines.append(f"PLATFORM: {platform}{header_suffix}")
        lines.append(f"{'Site Name':<30} | {'Cap(kWp)':<8} | {'Pwr(kW)':<8} | {'Cap.Util%':<9} | {'Status':<10} | {'Last Data':<10} |")
        lines.append(f"{'-'*30}-|-{'-'*8}-|-{'-'*8}-|-{'-'*9}-|-{'-'*10}-|-{'-'*10}-|")

        for status, last_contact in items:
            is_comm_fail, _ = is_comm_failure(status)

            # Status string
            if is_comm_fail:
                status_str = "🔴 OFFLINE"
            elif not status.is_fully_operational:
                status_str = f"⚠️ {status.online_count}/{status.inverter_count} Warn" if status.inverter_count > 0 else "⚠️ WARN"
            else:
                status_str = "OK"

            # Capacity utilisation
            pr = calculate_pr(status)
            pr_str = f"{pr:.1f}" if pr is not None else "—"

            # Truncate site name
            name = (status.site_name[:27] + '..') if len(status.site_name) > 30 else status.site_name

            lines.append(f"{name:<30} | {status.installed_capacity_kw:<8.1f} | {status.total_power_kw:<8.1f} | {pr_str:<9} | {status_str:<10} | {last_contact:<10} |")
        
        lines.append("")
        
    # METER RECONCILIATION
    if meter_results:
        lines.extend([
            "-" * 60,
            f"METER RECONCILIATION (Today: {now.strftime('%Y-%m-%d')})",
            "-" * 60,
            f"{'Site':<30} | {'Inv kWh':<9} | {'Meter kWh':<9} | {'Loss%':<6} | {'Status':<12}",
            f"{'-'*30}-|-{'-'*9}-|-{'-'*9}-|-{'-'*6}-|-{'-'*12}-",
        ])
        for r in meter_results:
            inv_str  = f"{r.inverter_kwh:.1f}"     if r.inverter_kwh  is not None else "—"
            mtr_str  = f"{r.meter_export_kwh:.1f}" if r.meter_export_kwh is not None else "—"
            loss_str = f"{r.loss_factor_pct:.1f}%" if r.loss_factor_pct is not None else "—"

            if r.status == MeterComparisonStatus.OK:
                status_str = "OK"
            elif r.status == MeterComparisonStatus.DATA_MISSING:
                status_str = "— No data"
            elif r.status == MeterComparisonStatus.DISCREPANCY:
                status_str = "🔴 DISCREPANCY"
            elif r.status == MeterComparisonStatus.INVERTER_ONLY:
                status_str = "🟡 INV ONLY"
            elif r.status == MeterComparisonStatus.METER_ONLY:
                status_str = "🟡 METER ONLY"
            else:
                status_str = r.status.value

            name = (r.site_name[:27] + '..') if len(r.site_name) > 30 else r.site_name
            lines.append(
                f"{name:<30} | {inv_str:<9} | {mtr_str:<9} | {loss_str:<6} | {status_str:<12}"
            )
        lines.append("")

    return "\n".join(lines), comm_failures, partial_outages


def save_report(report: str, report_dir: str, logger: logging.Logger) -> Optional[str]:
    """Save report to file and return the filepath."""
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    filename = f"status_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    filepath = Path(report_dir) / filename
    
    with open(filepath, 'w') as f:
        f.write(report)
    
    logger.info(f"Report saved to: {filepath}")
    return str(filepath)


def upload_to_google_drive(filepath: str, config: dict, logger: logging.Logger) -> Optional[str]:
    """Upload report to Google Drive and return the webViewLink."""
    gdrive_config = config.get('google_drive', {})
    
    if not gdrive_config.get('enabled', False):
        return None
    
    folder_id = gdrive_config.get('folder_id', '')
    credentials_file = gdrive_config.get('credentials_file', 'credentials.json')
    
    if not folder_id:
        logger.warning("Google Drive folder_id not configured")
        return None
    
    try:
        from .google_drive import GoogleDriveUploader
        uploader = GoogleDriveUploader(folder_id, credentials_file)
        if uploader.authenticate():
            report_url = uploader.upload_report(filepath)
            if report_url:
                logger.info(f"Report uploaded to Google Drive: {report_url}")
                return report_url
            else:
                logger.warning("Failed to upload report to Google Drive")
        else:
            logger.warning("Google Drive authentication failed")
    except ImportError:
        logger.warning("Google Drive libraries not installed.")
    except Exception as e:
        logger.error(f"Google Drive upload error: {e}")
    return None


def send_email_notification(report: str, config: dict, logger: logging.Logger):
    """Send report via email if configured."""
    email_config = config.get('email', {})
    
    if not email_config.get('enabled', False):
        return
    
    try:
        from .email_notifier import EmailNotifier
        notifier = EmailNotifier(email_config)
        
        is_valid, error_msg = notifier.validate_config()
        if not is_valid:
            logger.warning(f"Email notification not configured: {error_msg}")
            return
        
        subject = f"Inverter Status Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        if notifier.send_report(subject, report):
            logger.info("Report sent via email")
        else:
            logger.warning("Failed to send report via email")
            
    except Exception as e:
        logger.error(f"Email notification error: {e}")


def handle_notifications(config: dict, comm_fails: list, partials: list, logger: logging.Logger, report_url: Optional[str] = None, skip_state_save: bool = False):
    """Send notifications if critical alerts are present."""
    if not comm_fails and not partials:
        return
        
    notifier = NotificationManager(config)
    summary = f"INVERTER ALERT: {len(comm_fails)} OFFLINE, {len(partials)} DEGRADED"
    
    # Build current issues dict for deduplication (site_id -> description)
    current_issues = {}
    body_lines = [summary, "-" * len(summary)]
    for status, last_contact in comm_fails:
        current_issues[status.site_id] = f"{status.site_name} (OFFLINE, Last: {last_contact})"
        body_lines.append(f"🔴 {status.site_name} (OFFLINE, Last: {last_contact})")
    for status in partials:
        current_issues[status.site_id] = f"{status.site_name} ({status.online_count}/{status.inverter_count} Online)"
        body_lines.append(f"🟡 {status.site_name} ({status.online_count}/{status.inverter_count} Online)")
    
    if report_url:
        body_lines.append(f"\nFull Report: {report_url}")
        
    notifier.send_alert(summary, "\n".join(body_lines), current_issues, allow_state_save=not skip_state_save)


def check_all_inverters(config: dict, logger: logging.Logger, save_to_file: bool = True, skip_state_save: bool = False):
    """Main function to check all inverters and generate report."""
    logger.info("Starting inverter status check...")
    
    clients = get_enabled_clients(config, logger)
    if not clients:
        logger.error("No platforms enabled. Enable at least one platform in config.yaml")
        return
    
    all_statuses = []
    
    for client in clients:
        logger.info(f"Checking {client.PLATFORM_NAME}...")
        try:
            statuses = client.get_all_status()
            all_statuses.extend(statuses)
            logger.info(f"  Found {len(statuses)} site(s)")
        except Exception as e:
            logger.error(f"Error checking {client.PLATFORM_NAME}: {e}")
            all_statuses.append(SiteStatus(
                site_id="error",
                site_name="Error",
                platform=client.PLATFORM_NAME,
                error_message=str(e)
            ))
    
    # Run meter vs inverter comparison
    meter_results = []
    meter_checker = MeterChecker(config)
    if meter_checker.enabled:
        try:
            meter_results = meter_checker.check_all(all_statuses)
            logger.info(f"Meter comparison: {len(meter_results)} site(s) checked")
        except Exception as e:
            logger.error(f"Meter comparison failed: {e}")

    # Generate and print report
    report_text, comm_fails, partials = generate_report(all_statuses, logger, meter_results)
    print(report_text)
    
    report_url = None
    # Save to file and upload to Google Drive EARLIER so we have the link
    if save_to_file:
        report_dir = config.get('report_directory', './reports')
        filepath = save_report(report_text, report_dir, logger)
        
        # Upload to Google Drive and get URL
        if filepath:
            report_url = upload_to_google_drive(filepath, config, logger)
    
    # Raise contractor tickets for new offline/degraded sites and meter issues
    ticket_gen = TicketGenerator(config)
    tickets_sent = ticket_gen.raise_new_tickets(comm_fails, partials, meter_results)
    if tickets_sent:
        logger.info(f"Raised {tickets_sent} contractor ticket(s).")

    # Sync live status to Notion Site Monitoring Status + Equipment Status databases
    notion_sync = NotionStatusSync(config)
    notion_sync.sync(all_statuses, comm_fails)

    # Notify if critical alerts exist (now with link)
    handle_notifications(config, comm_fails, partials, logger, report_url=report_url, skip_state_save=skip_state_save)
    
    # Send email notification (every time report is generated)
    send_email_notification(report_text, config, logger)
    
    # Send daily digest (now with link)
    notifier = NotificationManager(config)
    notifier.send_daily_digest(report_text, report_url=report_url, allow_state_save=not skip_state_save)
    
    logger.info("Status check complete.")


def generate_demo_report(logger: logging.Logger):
    """Generate a demo report with sample data."""
    now = datetime.now()
    yesterday_ts = int((now.timestamp() - 90000) * 1000) # > 24h
    recent_ts = int((now.timestamp() - 600) * 1000)   # 10 mins ago
    
    demo_statuses = [
        SiteStatus(
            site_id="demo-1",
            site_name="Man City Joie Stadium",
            platform="SolarEdge",
            installed_capacity_kw=500.0,
            inverters=[InverterStatus(f"INV-{i}", f"Inverter {i}", InverterState.ONLINE, 10.0, 50.0) for i in range(14)],
            total_power_kw=140.0,
            total_energy_today_kwh=700.0,
            last_data_time=str(recent_ts)
        ),
        SiteStatus(
            site_id="demo-2",
            site_name="Finlay Beverages",
            platform="Solis",
            installed_capacity_kw=1.6,
            inverters=[InverterStatus("INV-001", "Inverter 1", InverterState.ONLINE, 0.4, 1.0)] + 
                      [InverterStatus(f"INV-{i}", f"Inverter {i}", InverterState.WARNING, 0.05, 0.1) for i in range(2, 13)],
            total_power_kw=0.8,
            total_energy_today_kwh=2.0,
            last_data_time=str(recent_ts)
        ),
        SiteStatus(
            site_id="demo-3",
            site_name="desuez consett unit 4",
            platform="Solis",
            installed_capacity_kw=72.0,
            inverters=[InverterStatus("INV-001", "Inverter 1", InverterState.OFFLINE, 0.0, 0.0)],
            total_power_kw=0.0,
            total_energy_today_kwh=0.0,
            last_data_time=str(yesterday_ts - 86400 * 7) # 8 days ago
        ),
        SiteStatus(
            site_id="demo-4",
            site_name="Haverhill",
            platform="Solis",
            installed_capacity_kw=1.0,
            inverters=[InverterStatus(f"INV-{i}", f"Inverter {i}", InverterState.WARNING, 6.0, 10.0) for i in range(7)],
            total_power_kw=42.0, # Intentional high power demo
            total_energy_today_kwh=100.0,
            last_data_time=str(yesterday_ts)
        ),
    ]
    
    report_text, comm_fails, partials = generate_report(demo_statuses, logger)
    print(report_text)
    
    # For demo mode, try to send notification if enabled in env
    try:
        # Load config to get notification settings from env
        config = load_config()
        mock_url = "https://drive.google.com/file/d/demo-link/view"
        handle_notifications(config, comm_fails, partials, logger, report_url=mock_url, skip_state_save=True)
        
        # Test daily digest in demo if last_digest_date is not today
        notifier = NotificationManager(config)
        notifier.send_daily_digest(report_text, report_url=mock_url, allow_state_save=False)
    except Exception as e:
        logger.debug(f"Demo notification skipped: {e}")


def run_scheduler(config: dict, logger: logging.Logger):
    """Run the scheduler for periodic checks."""
    if not HAS_SCHEDULE:
        logger.error("'schedule' package not installed. Run: pip install schedule")
        sys.exit(1)
    
    interval_hours = config.get('polling_interval_hours', 2)
    logger.info(f"Starting scheduler - checking every {interval_hours} hour(s)")
    logger.info("Press Ctrl+C to stop")
    
    # Run immediately on start
    check_all_inverters(config, logger)
    
    # Schedule periodic runs
    schedule.every(interval_hours).hours.do(check_all_inverters, config, logger)
    
    try:
        while True:
            schedule.run_pending()
            import time
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")


def validate_config(config: dict, logger: logging.Logger):
    """Validate configuration file."""
    logger.info("Validating configuration...")
    
    platforms = config.get('platforms', {})
    enabled_count = 0
    
    for platform_name, platform_config in platforms.items():
        if not platform_config.get('enabled', False):
            logger.info(f"  {platform_name}: disabled")
            continue
        
        enabled_count += 1
        client_classes = {
            'solaredge': SolarEdgeClient,
            'solaredge_browser': SolarEdgeBrowserClient,
            'huawei': HuaweiClient,
            'solis': SolisClient,
            'sungrow': SungrowClient,
            'sungrow_browser': SungrowBrowserClient,
            'sungrow_web': SungrowWebClient,
        }
        
        client_class = client_classes.get(platform_name.lower())
        if not client_class:
            logger.warning(f"  {platform_name}: Unknown platform")
            continue
        
        try:
            client = client_class(platform_config)
            is_valid, error = client.validate_config()
            if is_valid:
                logger.info(f"  {platform_name}: ✓ valid")
            else:
                logger.warning(f"  {platform_name}: ✗ {error}")
        except Exception as e:
            logger.error(f"  {platform_name}: ✗ {e}")
    
    if enabled_count == 0:
        logger.warning("No platforms are enabled!")
    else:
        logger.info(f"Enabled platforms: {enabled_count}")
    
    logger.info("Validation complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor solar inverters across multiple platforms"
    )
    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '-s', '--schedule',
        action='store_true',
        help='Run continuously with scheduled checks'
    )
    parser.add_argument(
        '-v', '--validate',
        action='store_true',
        help='Validate configuration and exit'
    )
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run with demo data to see report format'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save report to file'
    )
    parser.add_argument(
        '--solar-check',
        action='store_true',
        help='Exit 0 if now is a solar-scheduled time, else exit 1'
    )
    parser.add_argument(
        '--test-email',
        action='store_true',
        help='Send a test email to verify SMTP configuration and exit'
    )
    parser.add_argument(
        '--test-ticket',
        action='store_true',
        help='Send a test fault ticket to verify contractor email configuration and exit'
    )
    parser.add_argument(
        '--seed-notion',
        action='store_true',
        help='Pre-populate Notion Site Monitoring Status from the AMPYR Asset Register and exit'
    )

    args = parser.parse_args()
    
    # Demo mode doesn't need config
    if args.demo:
        logger = setup_logging(log_to_file=False)
        generate_demo_report(logger)
        return
    
    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Setup logging
    logger = setup_logging(
        log_to_file=config.get('log_to_file', True),
        log_dir=config.get('log_directory', './logs')
    )
    
    # Test email mode
    if args.test_email:
        email_config = config.get('email', {})
        if not email_config.get('enabled', False):
            print("Email is not enabled in config.yaml (email.enabled: false).", file=sys.stderr)
            sys.exit(1)
        try:
            from .email_notifier import EmailNotifier
            notifier = EmailNotifier(email_config)
            is_valid, error_msg = notifier.validate_config()
            if not is_valid:
                print(f"Email configuration invalid: {error_msg}", file=sys.stderr)
                sys.exit(1)
            success = notifier.send_report(
                subject="Solar Monitoring — test email",
                report_text="This is a test email from Solar Monitoring.\n\nSMTP configuration is working correctly.",
            )
            if success:
                print(f"Test email sent to: {', '.join(notifier.to_emails)}")
                sys.exit(0)
            else:
                print("Failed to send test email. Check logs for details.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error sending test email: {e}", file=sys.stderr)
            sys.exit(1)

    # Test ticket mode
    if args.test_ticket:
        tg = TicketGenerator(config)
        if not tg.enabled:
            print(
                "tickets.enabled is false in config.yaml — set it to true to test.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            success = tg.send_test_ticket()
            if success:
                print("Test ticket sent.")
                sys.exit(0)
            else:
                print("Failed to send test ticket. Check logs for details.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error sending test ticket: {e}", file=sys.stderr)
            sys.exit(1)

    # Seed Notion mode
    if args.seed_notion:
        syncer = NotionStatusSync(config)
        try:
            count = syncer.seed_from_asset_register()
            print(f"Notion seed complete: {count} site row(s) created.")
            sys.exit(0)
        except Exception as e:
            print(f"Notion seed failed: {e}", file=sys.stderr)
            sys.exit(1)

    # Run appropriate mode
    if args.solar_check:
        now = datetime.now(timezone.utc)
        schedule_times = get_solar_schedule(logger, date=now)
        
        is_scheduled = False
        for t in schedule_times:
            # Allow 30-minute window for GitHub Actions variability
            delta = abs((now - t).total_seconds())
            if delta < 1800: # 30 mins
                is_scheduled = True
                break
        
        if is_scheduled:
            logger.info("Current time matches solar schedule.")
            sys.exit(0)
        else:
            # Find the next scheduled time for better logging
            next_run = None
            for t in schedule_times:
                if t > now:
                    next_run = t
                    break
            
            # If no runs left today, check tomorrow
            if not next_run:
                from datetime import timedelta
                tomorrow_times = get_solar_schedule(logger, date=now + timedelta(days=1))
                if tomorrow_times:
                    next_run = tomorrow_times[0]
            
            skip_msg = "Skipping: Outside solar reporting window."
            if next_run:
                skip_msg += f" Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M %Z')}"
            
            logger.info(skip_msg)
            sys.exit(1)
            
    if args.validate:
        validate_config(config, logger)
    elif args.schedule:
        run_scheduler(config, logger)
    else:
        check_all_inverters(config, logger, save_to_file=not args.no_save)


if __name__ == "__main__":
    main()
