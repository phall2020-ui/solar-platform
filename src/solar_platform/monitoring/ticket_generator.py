"""
Ticket generator for offline/degraded site alerts.

When a site goes offline or becomes degraded, this module generates a
maintenance ticket and emails it to the relevant O&M contractor.

Tickets are deduplicated — the same issue is not re-raised until the
configured dedup_hours window has elapsed (default 24 h).

Config (config.yaml):

  tickets:
    enabled: false
    dedup_hours: 24          # Don't re-raise the same issue within N hours
    from_email: peter.hall@ampyrde.com
    smtp_server: smtp.office365.com
    smtp_port: 587
    smtp_username: peter.hall@ampyrde.com
    smtp_password: <password>
    use_tls: true
    cc_emails:               # Optional — copies sent to these addresses too
      - peter.hall@ampyrde.com

  contractors:
    - name: ClearSol
      contact: Al Hicks
      email: al.hicks@clearsol.co.uk
      sites:                 # site_id values OR case-insensitive site_name substrings
        - "some-site-id"
        - "stadium"
    - name: SolPV
      contact: ""
      email: operations@solpv.co.uk
      sites: []              # Empty list = default fallback for all unmatched sites
"""

import json
import logging
import smtplib

import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple

from .clients.base import InverterState, MeterComparisonResult, MeterComparisonStatus, SiteStatus


TICKET_STATE_FILE = ".ticket_state.json"


class TicketGenerator:
    """Generates and sends O&M fault tickets for offline/degraded sites."""

    def __init__(self, config: dict):
        self.config = config.get("tickets", {})
        self.enabled = self.config.get("enabled", False)
        self.dedup_hours = self.config.get("dedup_hours", 24)
        self.contractors = config.get("contractors", [])
        self.state_file = Path(self.config.get("state_file", TICKET_STATE_FILE))
        self.logger = logging.getLogger(__name__)

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    # Meter issue dedup window — longer than comms failures (daily check)
    METER_DEDUP_HOURS = 72

    # Ticket policy per meter status
    _METER_TICKET_STATUSES = {
        MeterComparisonStatus.DISCREPANCY:   ("HIGH",   48),
        MeterComparisonStatus.INVERTER_ONLY: ("HIGH",   24),
        MeterComparisonStatus.METER_ONLY:    ("MEDIUM", 72),
    }

    # Notion issue type labels per meter status
    _METER_ISSUE_LABELS = {
        MeterComparisonStatus.DISCREPANCY:   "Meter Discrepancy",
        MeterComparisonStatus.INVERTER_ONLY: "Inverter Only",
        MeterComparisonStatus.METER_ONLY:    "Meter Only",
    }

    def raise_new_tickets(
        self,
        comm_fails: List[Tuple[SiteStatus, str]],
        partials: List[SiteStatus],
        meter_results: Optional[List[MeterComparisonResult]] = None,
    ) -> int:
        """
        Raise tickets for any newly detected issues.

        comm_fails:    list of (SiteStatus, last_contact_str) for communication failures
        partials:      list of SiteStatus for partial outages
        meter_results: optional list of MeterComparisonResult; tickets raised for
                       DISCREPANCY, INVERTER_ONLY, and METER_ONLY statuses

        Returns the number of tickets sent.
        """
        if not self.enabled:
            return 0

        state = self._load_state()
        now = datetime.now()
        sent = 0

        for site_status, last_contact in comm_fails:
            key = f"comm_{site_status.site_id}"
            if self._should_raise(key, state, now):
                contractor = self._find_contractor(site_status)
                ref = self._next_ref(state, now)
                body = self._format_comm_failure(ref, site_status, last_contact, now, contractor)
                if self._send(ref, site_status.site_name, body, contractor):
                    state["sent"][key] = now.isoformat()
                    sent += 1
                    self._log_to_notion(ref, site_status.site_name, site_status.platform,
                                        "CRITICAL", "Comm Failure", contractor, now, 24)
                elif contractor is None:
                    # Log once but don't keep retrying if no contractor configured
                    state["sent"][key] = now.isoformat()

        for site_status in partials:
            key = f"partial_{site_status.site_id}"
            if self._should_raise(key, state, now):
                contractor = self._find_contractor(site_status)
                ref = self._next_ref(state, now)
                body = self._format_partial_outage(ref, site_status, now, contractor)
                if self._send(ref, site_status.site_name, body, contractor):
                    state["sent"][key] = now.isoformat()
                    sent += 1
                    self._log_to_notion(ref, site_status.site_name, site_status.platform,
                                        "HIGH", "Partial Outage", contractor, now, 48)
                elif contractor is None:
                    state["sent"][key] = now.isoformat()

        for result in (meter_results or []):
            if result.status not in self._METER_TICKET_STATUSES:
                continue
            key = f"meter_{result.status.value}_{result.site_id}"
            if self._should_raise(key, state, now, override_hours=self.METER_DEDUP_HOURS):
                priority, sla_hours = self._METER_TICKET_STATUSES[result.status]
                issue_label = self._METER_ISSUE_LABELS[result.status]
                stub = SimpleNamespace(site_id=result.site_id, site_name=result.site_name)
                contractor = self._find_contractor(stub)
                ref = self._next_ref(state, now)
                body = self._format_meter_issue(ref, result, priority, sla_hours, now, contractor)
                if self._send(ref, result.site_name, body, contractor):
                    state["sent"][key] = now.isoformat()
                    sent += 1
                    self._log_to_notion(ref, result.site_name, result.platform,
                                        priority, issue_label, contractor, now, sla_hours)
                elif contractor is None:
                    state["sent"][key] = now.isoformat()

        self._save_state(state)
        if sent:
            self.logger.info(f"Ticket generator: {sent} ticket(s) raised.")
        else:
            self.logger.info("Ticket generator: no new tickets to raise.")
        return sent

    # -----------------------------------------------------------------------
    # Ticket body formatting
    # -----------------------------------------------------------------------

    def _sla_deadline(self, raised_at: datetime, hours: int) -> str:
        return (raised_at + timedelta(hours=hours)).strftime("%d %b %Y %H:%M")

    def _format_comm_failure(
        self,
        ref: str,
        status: SiteStatus,
        last_contact: str,
        now: datetime,
        contractor: Optional[dict] = None,
    ) -> str:
        if contractor is None:
            contractor = self._find_contractor(status)
        contact_name = contractor.get("contact", "") if contractor else ""
        greeting = f"Hi {contact_name}," if contact_name else "Hi,"
        cap_str = (
            f"{status.installed_capacity_kw:.1f} kWp"
            if status.installed_capacity_kw > 0
            else "Unknown"
        )

        return f"""{greeting}

Please see the fault ticket below.

FAULT TICKET
============
Ref:       {ref}
Priority:  CRITICAL
Raised:    {now.strftime("%d %b %Y %H:%M")}
SLA:       By {self._sla_deadline(now, 24)} (24 h)

SITE DETAILS
------------
Site:      {status.site_name}
Platform:  {status.platform}
Capacity:  {cap_str}
Issue:     Communication failure — no data received for more than 24 hours
Last data: {last_contact or "Unknown"}

REQUESTED ACTION
----------------
Please investigate and confirm the site status. If the inverter(s) are
offline, carry out fault diagnosis and restore generation where possible.
Provide an update by the SLA deadline above.

Best,
Peter Hall
Asset Manager, AMPYR Distributed Energy
peter.hall@ampyrde.com
"""

    def _format_partial_outage(
        self,
        ref: str,
        status: SiteStatus,
        now: datetime,
        contractor: Optional[dict] = None,
    ) -> str:
        if contractor is None:
            contractor = self._find_contractor(status)
        contact_name = contractor.get("contact", "") if contractor else ""
        greeting = f"Hi {contact_name}," if contact_name else "Hi,"
        cap_str = (
            f"{status.installed_capacity_kw:.1f} kWp"
            if status.installed_capacity_kw > 0
            else "Unknown"
        )

        problem_inverters = [
            inv
            for inv in status.inverters
            if inv.state in (InverterState.OFFLINE, InverterState.WARNING)
        ]
        inv_lines = "\n".join(
            f"  - {inv.name}: {inv.state.value.upper()}"
            + (f" ({inv.error_message})" if inv.error_message else "")
            for inv in problem_inverters[:10]
        )
        if len(problem_inverters) > 10:
            inv_lines += f"\n  ... and {len(problem_inverters) - 10} more"
        if not inv_lines:
            inv_lines = "  (No inverter-level detail available)"

        return f"""{greeting}

Please see the fault ticket below.

FAULT TICKET
============
Ref:       {ref}
Priority:  HIGH
Raised:    {now.strftime("%d %b %Y %H:%M")}
SLA:       By {self._sla_deadline(now, 48)} (48 h)

SITE DETAILS
------------
Site:      {status.site_name}
Platform:  {status.platform}
Capacity:  {cap_str}
Issue:     Partial outage — {status.online_count}/{status.inverter_count} inverters online
Power:     {status.total_power_kw:.1f} kW / {status.installed_capacity_kw:.1f} kWp

AFFECTED INVERTERS
------------------
{inv_lines}

REQUESTED ACTION
----------------
Please investigate the affected inverters. Provide an update by the SLA
deadline above, including the cause and expected resolution date.

Best,
Peter Hall
Asset Manager, AMPYR Distributed Energy
peter.hall@ampyrde.com
"""

    def _format_meter_issue(
        self,
        ref: str,
        result: MeterComparisonResult,
        priority: str,
        sla_hours: int,
        now: datetime,
        contractor: Optional[dict] = None,
    ) -> str:
        if contractor is None:
            stub = SimpleNamespace(site_id=result.site_id, site_name=result.site_name)
            contractor = self._find_contractor(stub)
        contact_name = contractor.get("contact", "") if contractor else ""
        greeting = f"Hi {contact_name}," if contact_name else "Hi,"
        cap_str = "Unknown"

        inv_str  = f"{result.inverter_kwh:.1f} kWh"  if result.inverter_kwh  is not None else "Unknown"
        mtr_str  = f"{result.meter_export_kwh:.1f} kWh" if result.meter_export_kwh is not None else "Unknown"
        loss_str = f"{result.loss_factor_pct:.1f}%" if result.loss_factor_pct is not None else "Unknown"

        if result.status == MeterComparisonStatus.DISCREPANCY:
            issue_line = (
                f"Meter vs inverter discrepancy — loss factor {loss_str} "
                f"(expected ~5%, threshold +20%)"
            )
            action_line = (
                "Please investigate the discrepancy between inverter generation and "
                "grid export. Check for ELS curtailment, consumption anomaly, or "
                "metering fault. Provide findings by the SLA deadline above."
            )
        elif result.status == MeterComparisonStatus.INVERTER_ONLY:
            issue_line = (
                f"Inverter reports {inv_str} generated but meter shows {mtr_str} exported. "
                "Possible ELS export limitation or metering fault."
            )
            action_line = (
                "Please investigate why the meter is not recording expected export. "
                "Check ELS settings, CT clamp orientation, and meter comms. "
                "Provide findings by the SLA deadline above."
            )
        else:  # METER_ONLY
            issue_line = (
                f"Meter shows {mtr_str} exported but inverter monitoring shows {inv_str}. "
                "Possible inverter monitoring gap or data latency issue."
            )
            action_line = (
                "Please confirm whether the inverter is generating correctly and "
                "investigate the monitoring data gap. Provide findings by the SLA deadline above."
            )

        return f"""{greeting}

Please see the fault ticket below.

FAULT TICKET
============
Ref:       {ref}
Priority:  {priority}
Raised:    {now.strftime("%d %b %Y %H:%M")}
SLA:       By {self._sla_deadline(now, sla_hours)} ({sla_hours} h)

SITE DETAILS
------------
Site:      {result.site_name}
Platform:  {result.platform}
Issue:     {issue_line}

Inverter generation today:  {inv_str}
Meter export today:         {mtr_str}

REQUESTED ACTION
----------------
{action_line}

Best,
Peter Hall
Asset Manager, AMPYR Distributed Energy
peter.hall@ampyrde.com
"""

    def send_test_ticket(self) -> bool:
        """
        Send a clearly marked test ticket to verify SMTP and contractor config.

        Uses the default contractor (first entry with an empty sites list, or
        the first contractor overall if none are marked as default).
        Returns True if the email was sent successfully.
        """
        if not self.contractors:
            self.logger.warning("No contractors configured in config.yaml — nothing to test.")
            return False

        now = datetime.now()
        stub = SimpleNamespace(
            site_id="test-site",
            site_name="Test Site (DO NOT ACTION)",
            platform="Test",
            installed_capacity_kw=250.0,
            inverters=[],
            online_count=0,
            inverter_count=0,
            total_power_kw=0.0,
        )
        contractor = self._find_contractor(stub)
        if not contractor:
            # No default — use first configured contractor
            contractor = self.contractors[0]

        ref = f"TEST-{now.strftime('%Y%m%d-%H%M')}"
        body = (
            "[THIS IS A TEST TICKET — NO ACTION REQUIRED]\n\n"
            + self._format_comm_failure(
                ref, stub, now.strftime("%Y-%m-%d %H:%M"), now, contractor
            )
        )
        return self._send(ref, stub.site_name, body, contractor)

    # -----------------------------------------------------------------------
    # Contractor lookup
    # -----------------------------------------------------------------------

    def _find_contractor(self, status: SiteStatus) -> Optional[dict]:
        """
        Return the contractor for a site.

        Match order:
          1. Exact site_id match in contractor.sites
          2. Case-insensitive site_name substring match in contractor.sites
          3. First contractor with an empty sites list (default fallback)
          4. None if no contractors configured
        """
        default = None
        for contractor in self.contractors:
            sites = contractor.get("sites", [])
            if not sites:
                if default is None:
                    default = contractor
                continue
            for pattern in sites:
                if pattern == status.site_id:
                    return contractor
                if pattern.lower() in status.site_name.lower():
                    return contractor
        return default

    # -----------------------------------------------------------------------
    # Email sending
    # -----------------------------------------------------------------------

    def _send(
        self,
        ref: str,
        site_name: str,
        body: str,
        contractor: Optional[dict],
    ) -> bool:
        if not contractor:
            self.logger.warning(
                f"No contractor configured for '{site_name}'. "
                f"Ticket {ref} not sent — add an entry to contractors in config.yaml."
            )
            return False

        to_email = contractor.get("email", "").strip()
        if not to_email:
            self.logger.warning(
                f"Contractor '{contractor.get('name')}' has no email address. "
                f"Ticket {ref} not sent."
            )
            return False

        smtp_server = self.config.get("smtp_server", "")
        smtp_port = self.config.get("smtp_port", 587)
        smtp_username = self.config.get("smtp_username", "")
        smtp_password = self.config.get("smtp_password", "")
        from_email = self.config.get("from_email", smtp_username)
        use_tls = self.config.get("use_tls", True)
        cc_emails = self.config.get("cc_emails", [])

        if not smtp_server:
            self.logger.warning(
                f"tickets.smtp_server not configured. Ticket {ref} not sent."
            )
            return False

        subject = f"[{ref}] Site fault — {site_name}"
        recipients = [to_email] + [e for e in cc_emails if e]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        if cc_emails:
            msg["Cc"] = ", ".join(e for e in cc_emails if e)
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = None
        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
            if use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.sendmail(from_email, recipients, msg.as_string())
            self.logger.info(
                f"Ticket {ref} sent to {to_email} "
                f"({'+ CC' if cc_emails else 'no CC'}) for site '{site_name}'"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send ticket {ref} to {to_email}: {e}")
            return False
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    # -----------------------------------------------------------------------
    # Notion logging
    # -----------------------------------------------------------------------

    def _log_to_notion(
        self,
        ref: str,
        site_name: str,
        platform: str,
        priority: str,
        issue_type: str,
        contractor: Optional[dict],
        raised_at: datetime,
        sla_hours: int,
    ) -> None:
        """
        Create a row in the Notion O&M Fault Tickets database for a raised ticket.
        Silently skips if notion is not configured or the API call fails.

        Config (under tickets.notion in config.yaml):
          notion:
            enabled: true
            token: <Notion integration token>
            database_id: b8c032a1e2e84349a81d0fff0befa6c8
        """
        notion_cfg = self.config.get("notion", {})
        if not notion_cfg.get("enabled", False):
            return

        token = notion_cfg.get("token", "").strip()
        database_id = notion_cfg.get("database_id", "").strip()
        if not token or not database_id:
            self.logger.warning(
                "tickets.notion.enabled is true but token or database_id is missing."
            )
            return

        contractor_str = ""
        if contractor:
            name = contractor.get("name", "")
            contact = contractor.get("contact", "")
            contractor_str = f"{name} — {contact}" if contact else name

        sla_deadline = raised_at + timedelta(hours=sla_hours)

        # Normalise platform to a value the Notion select accepts; fall back to "Other"
        valid_platforms = {"SolarEdge", "Huawei", "Solis", "Sungrow", "Juggle"}
        platform_value = platform if platform in valid_platforms else "Other"

        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Ref":         {"title":     [{"text": {"content": ref}}]},
                "Site":        {"rich_text": [{"text": {"content": site_name}}]},
                "Platform":    {"select":    {"name": platform_value}},
                "Priority":    {"select":    {"name": priority}},
                "Issue Type":  {"select":    {"name": issue_type}},
                "Contractor":  {"rich_text": [{"text": {"content": contractor_str}}]},
                "Raised":      {"date":      {"start": raised_at.strftime("%Y-%m-%dT%H:%M:%S")}},
                "SLA Deadline":{"date":      {"start": sla_deadline.strftime("%Y-%m-%dT%H:%M:%S")}},
                "Status":      {"select":    {"name": "Open"}},
            },
        }

        try:
            resp = requests.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            self.logger.info(f"Ticket {ref} logged to Notion.")
        except Exception as e:
            self.logger.warning(f"Failed to log ticket {ref} to Notion: {e}")

    # -----------------------------------------------------------------------
    # State / deduplication
    # -----------------------------------------------------------------------

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sent": {}, "counter": 0, "last_date": None}

    def _save_state(self, state: dict):
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save ticket state: {e}")

    def _should_raise(self, key: str, state: dict, now: datetime, override_hours: Optional[int] = None) -> bool:
        """Return True if this issue has not been ticketed within dedup_hours (or override_hours)."""
        window = (override_hours or self.dedup_hours) * 3600
        sent = state.get("sent", {})
        if key not in sent:
            return True
        try:
            last_sent = datetime.fromisoformat(sent[key])
            return (now - last_sent).total_seconds() > window
        except Exception:
            return True

    def _next_ref(self, state: dict, now: datetime) -> str:
        """Return a ticket ref like TICKET-20260325-001, incrementing the daily counter."""
        today = now.strftime("%Y%m%d")
        if state.get("last_date") != today:
            state["counter"] = 0
            state["last_date"] = today
        state["counter"] = state.get("counter", 0) + 1
        return f"TICKET-{today}-{state['counter']:03d}"
