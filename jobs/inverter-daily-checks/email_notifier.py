"""
Email notification module for sending inverter status reports.

Supports SMTP email delivery with configurable settings.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Tuple


class EmailNotifier:
    """Email notification handler for inverter monitoring reports."""
    
    def __init__(self, config: dict):
        """
        Initialize email notifier with SMTP configuration.
        
        Args:
            config: Dictionary containing email settings:
                - smtp_server: SMTP server hostname
                - smtp_port: SMTP server port (default: 587)
                - smtp_username: SMTP authentication username
                - smtp_password: SMTP authentication password
                - from_email: Sender email address
                - to_emails: List of recipient email addresses
                - use_tls: Whether to use TLS (default: True)
        """
        self.smtp_server = config.get('smtp_server', '')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_username = config.get('smtp_username', '')
        self.smtp_password = config.get('smtp_password', '')
        self.from_email = config.get('from_email', '')
        self.to_emails = config.get('to_emails', [])
        self.use_tls = config.get('use_tls', True)
        self.logger = logging.getLogger(__name__)
    
    def validate_config(self) -> Tuple[bool, str]:
        """Validate that required email configuration is present."""
        if not self.smtp_server:
            return False, "SMTP server not configured"
        if not self.from_email:
            return False, "From email not configured"
        if not self.to_emails:
            return False, "Recipient emails not configured"
        return True, ""
    
    def send_report(self, subject: str, report_text: str) -> bool:
        """
        Send report via email.
        
        Args:
            subject: Email subject line
            report_text: Plain text report content
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        is_valid, error_msg = self.validate_config()
        if not is_valid:
            self.logger.warning(f"Email configuration invalid: {error_msg}")
            return False
        
        server = None
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = ', '.join(self.to_emails)
            
            # Attach plain text version
            text_part = MIMEText(report_text, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Connect to SMTP server
            self.logger.info(f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            
            if self.use_tls:
                server.starttls()
            
            # Login if credentials provided
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            
            # Send email
            server.sendmail(self.from_email, self.to_emails, msg.as_string())
            
            self.logger.info(f"Report sent to {len(self.to_emails)} recipient(s)")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            return False
        finally:
            # Ensure SMTP connection is properly closed
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
