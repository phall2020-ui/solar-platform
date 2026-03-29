"""
Google Drive upload helper for Inverter Monitoring.

Uses a service account or OAuth2 credentials to upload report files.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False

# Scopes for Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']


class GoogleDriveUploader:
    """Upload files to Google Drive."""
    
    def __init__(self, folder_id: str, credentials_path: Optional[str] = None):
        """
        Initialize uploader.
        
        Args:
            folder_id: Google Drive folder ID to upload to
            credentials_path: Path to credentials.json (OAuth2) or service account JSON
        """
        self.folder_id = folder_id
        self.credentials_path = os.path.expanduser(credentials_path or "credentials.json")
        self.token_path = os.path.expanduser("~/Secrets/google/token.json")
        self.service = None
        self.logger = logging.getLogger(__name__)
        self._authenticated = False
    
    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        if not HAS_GOOGLE_API:
            print("Google API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
            return False
        
        creds = None
        
        # Check for existing token
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                pass
        
        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                # Check for service account JSON
                if os.path.exists(self.credentials_path):
                    try:
                        # Try as service account first
                        creds = service_account.Credentials.from_service_account_file(
                            self.credentials_path, scopes=SCOPES
                        )
                    except Exception:
                        # Try as OAuth2 client credentials
                        try:
                            flow = InstalledAppFlow.from_client_secrets_file(
                                self.credentials_path, SCOPES
                            )
                            creds = flow.run_local_server(port=0)
                        except Exception as e:
                            print(f"Failed to authenticate: {e}")
                            return False
                else:
                    print(f"Credentials file not found: {self.credentials_path}")
                    return False
            
            # Save token for reuse
            if hasattr(creds, 'refresh_token') and creds.refresh_token:
                try:
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                except Exception:
                    pass
        
        try:
            self.service = build('drive', 'v3', credentials=creds)
            self._authenticated = True
            return True
        except Exception as e:
            print(f"Failed to build Drive service: {e}")
            return False
    
    def upload_file(self, file_path: str, mime_type: str = 'text/plain') -> Optional[str]:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Local path to file
            mime_type: MIME type of file
            
        Returns:
            File ID if successful, None otherwise
        """
        if not self._authenticated or not self.service:
            if not self.authenticate():
                return None
        
        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {file_path}")
            return None
        
        try:
            file_metadata = {
                'name': path.name,
                'parents': [self.folder_id]
            }
            
            media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            print(f"Uploaded: {file.get('name')} -> {file.get('webViewLink', 'N/A')}")
            return file.get('webViewLink')
        
        except Exception as e:
            self.logger.error(f"Upload failed for {file_path}: {e}")
            return None
    
    def upload_report(self, report_path: str) -> Optional[str]:
        """Upload a report file to Google Drive and return its webViewLink."""
        return self.upload_file(report_path, 'text/plain')

    def download_file(self, filename: str, local_path: str) -> bool:
        """Download a file from the configured folder by name."""
        if not self._authenticated or not self.service:
            if not self.authenticate():
                return False
                
        try:
            # Search for file in folder
            query = f"name = '{filename}' and '{self.folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if not items:
                self.logger.debug(f"File not found in Drive: {filename}")
                return False
                
            file_id = items[0]['id']
            request = self.service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as f:
                request.execute()
            
            self.logger.info(f"Downloaded state file: {filename}")
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to download {filename}: {e}")
            return False
    
    def update_file(self, filename: str, local_path: str, mime_type: str = 'application/json') -> bool:
        """Update (overwrite) an existing file or create new one."""
        if not self._authenticated or not self.service:
            if not self.authenticate():
                return False

        try:
            # Search for existing file
            query = f"name = '{filename}' and '{self.folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            items = results.get('files', [])
            
            media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
            
            if items:
                # Update existing
                file_id = items[0]['id']
                self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                self.logger.info(f"Updated state file in Drive: {filename}")
            else:
                # Create new
                file_metadata = {
                    'name': filename,
                    'parents': [self.folder_id]
                }
                self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                self.logger.info(f"Created state file in Drive: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update {filename}: {e}")
            return False


def upload_to_drive(file_path: str, folder_id: str, credentials_path: str = "credentials.json") -> bool:
    """
    Convenience function to upload a file to Google Drive.
    
    Args:
        file_path: Local path to file  
        folder_id: Google Drive folder ID
        credentials_path: Path to credentials file
        
    Returns:
        True if successful
    """
    uploader = GoogleDriveUploader(folder_id, credentials_path)
    return uploader.upload_file(file_path) is not None
