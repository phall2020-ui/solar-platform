"""
solar_platform.monitoring
=========================

Operational monitoring daemon — absorbed from the standalone Solar-Monitoring repo.

Entry point: solar-monitor (cli/monitor.py) → daemon.py

Provides:
  monitoring.clients.*       — platform API clients (SolarEdge, Solis, Huawei, Juggle, Sungrow)
  monitoring.daemon          — main poll loop (run once or --schedule mode)
  monitoring.meter           — inverter vs grid-meter reconciliation
  monitoring.tickets         — O&M fault ticket generation with deduplication
  monitoring.notion_sync     — operational status sync to Notion
  monitoring.notifications   — multi-channel alerts (ntfy, webhook, email)
  monitoring.email_notifier  — SMTP report delivery
  monitoring.google_drive    — Google Drive report upload
"""
