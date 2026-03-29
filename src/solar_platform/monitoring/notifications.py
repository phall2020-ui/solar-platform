import logging
import requests
import smtplib
import json
from email.mime.text import MIMEText
from typing import List, Optional
from pathlib import Path

class NotificationManager:
    """Manages sending notifications across different providers."""
    
    STATE_FILE = ".alert_state.json"
    
    def __init__(self, config: dict):
        self.config = config.get('notifications', {})
        self.logger = logging.getLogger(__name__)
        self.enabled = self.config.get('enabled', False)
        self.state_file = Path(self.config.get('state_file', self.STATE_FILE))
        self.gdrive_enabled = config.get('google_drive', {}).get('enabled', False)
        self.gdrive_config = config.get('google_drive', {})
        
        # Try to sync state from Drive on init
        if self.gdrive_enabled:
            self._sync_from_drive()
    
    def _sync_from_drive(self):
        """Attempt to download state file from Google Drive."""
        try:
            from .google_drive import GoogleDriveUploader
            folder_id = self.gdrive_config.get('folder_id')
            creds = self.gdrive_config.get('credentials_file')
            
            if folder_id:
                uploader = GoogleDriveUploader(folder_id, creds)
                if uploader.download_file("alert_state.json", str(self.state_file)):
                    self.logger.info("Synced alert state from Google Drive")
        except Exception as e:
            self.logger.warning(f"Failed to sync state from Drive: {e}")

    def _load_state(self) -> dict:
        """Load previous alert state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"alerted_sites": {}, "last_digest_date": None, "last_alert_date": None}
    
    def _save_state(self, state: dict):
        """Save current alert state and sync to Drive."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
            
            # Sync to Drive
            if self.gdrive_enabled:
                from .google_drive import GoogleDriveUploader
                folder_id = self.gdrive_config.get('folder_id')
                creds = self.gdrive_config.get('credentials_file')
                
                if folder_id:
                    uploader = GoogleDriveUploader(folder_id, creds)
                    uploader.update_file("alert_state.json", str(self.state_file))
                    
        except Exception as e:
            self.logger.warning(f"Could not save alert state: {e}")
    
    def _should_send_daily_digest(self, state: dict) -> bool:
        """Check if we should send the daily digest (once per day)."""
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        return state.get('last_digest_date') != today
    
    def send_alert(self, summary: str, body: str, current_issues: Optional[dict] = None, allow_state_save: bool = True):
        """Send alert to all configured providers, with deduplication (resets daily)."""
        if not self.enabled:
            return
        
        # Deduplication logic
        if current_issues:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            
            state = self._load_state()
            last_alert_date = state.get("last_alert_date")
            
            # Reset daily - if it's a new day, we want to alert on EVERYTHING in the first run
            if last_alert_date != today:
                self.logger.info("New day detected. Resetting alert deduplication state.")
                prev_sites = set()
                # If it's a fresh day, we send the FULL list as a "Daily Reset" alert
                is_daily_reset = True
            else:
                prev_sites = set(state.get("alerted_sites", {}).keys())
                is_daily_reset = False
            
            curr_sites = set(current_issues.keys())
            new_sites = curr_sites - prev_sites
            
            if not new_sites:
                self.logger.info("No new issues detected. Skipping notification.")
                # Still update state in case issues resolved
                if allow_state_save:
                    state["alerted_sites"] = current_issues
                    self._save_state(state)
                return
            
            # Format notification based on whether it's the first of the day or just new issues
            if is_daily_reset:
                summary = f"MORNING STATUS: {len(curr_sites)} site(s) with issues"
                body_lines = [f"🚨 {summary}", "-" * len(summary)]
                for site_id, desc in current_issues.items():
                    body_lines.append(f"⚠️ {desc}")
                body = "\n".join(body_lines)
            else:
                self.logger.info(f"New issues detected: {new_sites}")
                summary = f"NEW ALERT: {len(new_sites)} new site(s)"
                body_lines = [f"🆕 {summary}", "-" * len(summary)]
                for site_id in new_sites:
                    body_lines.append(f"🆕 {current_issues[site_id]}")
                body = "\n".join(body_lines)
            
            # Update state
            if allow_state_save:
                state["alerted_sites"] = current_issues
                state["last_alert_date"] = today
                self._save_state(state)
            
        self.logger.info("Sending critical alert notifications...")
        self._dispatch_notification(summary, body)
    
    def send_daily_digest(self, report_text: str, report_url: Optional[str] = None, allow_state_save: bool = True):
        """Send daily digest with full status report (once per day)."""
        if not self.enabled:
            return
            
        state = self._load_state()
        if not self._should_send_daily_digest(state):
            self.logger.info("Daily digest already sent today. Skipping.")
            return
        
        from datetime import datetime
        summary = f"Daily Solar Fleet Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # Truncate report for notification (ntfy has limits)
        max_len = 4000
        body = "📊 " + report_text[:max_len] + ("..." if len(report_text) > max_len else "")
        
        if report_url:
            body += f"\n\nFull Report: {report_url}"
        
        self.logger.info("Sending daily digest notification...")
        self._dispatch_notification(summary, body)
        
        # Update state
        if allow_state_save:
            state['last_digest_date'] = datetime.now().strftime('%Y-%m-%d')
            self._save_state(state)
    
    def _dispatch_notification(self, summary: str, body: str):
        """Send notification to all configured providers."""
        
        # NTFY.sh (Easiest for push notifications)
        if self.config.get('ntfy', {}).get('enabled'):
            self._send_ntfy(summary, body)
            
        # Webhook (Slack/Discord/General)
        if self.config.get('webhook', {}).get('enabled'):
            self._send_webhook(summary, body)
            
    def _send_ntfy(self, summary: str, body: str):
        """Send notification via ntfy.sh."""
        config = self.config.get('ntfy', {})
        topic = config.get('topic')
        if not topic:
            self.logger.warning("ntfy: topic not configured")
            return
            
        url = f"https://ntfy.sh/{topic}"
        try:
            headers = {
                "Title": summary,
                "Priority": "high",
                "Tags": "warning,solar_panel"
            }
            response = requests.post(url, data=body, headers=headers, timeout=10)
            response.raise_for_status()
            self.logger.info("ntfy: Notification sent")
        except Exception as e:
            self.logger.error(f"ntfy: Failed to send - {e}")

    def _send_webhook(self, summary: str, body: str):
        """Send notification via generic webhook."""
        config = self.config.get('webhook', {})
        url = config.get('url')
        if not url:
            self.logger.warning("webhook: url not configured")
            return
            
        try:
            # Generic payload that works for Slack/Discord/etc.
            payload = {"text": f"*{summary}*\n\n{body}"}
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            self.logger.info("webhook: Notification sent")
        except Exception as e:
            self.logger.error(f"webhook: Failed to send - {e}")

    def _send_email(self, summary: str, body: str):
        """Send notification via SMTP."""
        config = self.config.get('email', {})
        required = ['smtp_server', 'smtp_port', 'username', 'password', 'to_address']
        if not all(config.get(k) for k in required):
            self.logger.warning("email: SMTP configuration incomplete")
            return
            
        msg = MIMEText(body)
        msg['Subject'] = summary
        msg['From'] = config.get('from_address', config.get('username'))
        msg['To'] = config.get('to_address')
        
        try:
            with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
                server.starttls()
                server.login(config['username'], config['password'])
                server.send_message(msg)
            self.logger.info("email: Notification sent")
        except Exception as e:
            self.logger.error(f"email: Failed to send - {e}")
