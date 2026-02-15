"""
REST API Service for Solar Portfolio Manager.
Provides API endpoints for external integrations and programmatic access.
"""
import hashlib
import secrets
import sqlite3
from pathlib import Path

import pandas as pd


class APIKey:
    """API Key model."""
    def __init__(self, key_id: int, user_id: int, key_hash: str,
                 name: str, permissions: str, is_active: bool = True,
                 created_at: str = None, last_used: str = None):
        self.key_id = key_id
        self.user_id = user_id
        self.key_hash = key_hash
        self.name = name
        self.permissions = permissions.split(',') if isinstance(permissions, str) else permissions
        self.is_active = is_active
        self.created_at = created_at
        self.last_used = last_used


class APIService:
    """Service for managing API keys and handling API requests."""

    def __init__(self, toolkit_db: Path, reporting_db: Path,
                 api_db: Path | None = None):
        """Initialize API service."""
        if api_db is None:
            api_db = Path.home() / ".solar_toolkit" / "api.db"

        self.api_db = api_db
        self.toolkit_db = toolkit_db
        self.reporting_db = reporting_db
        self.api_db.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize API database."""
        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        # API Keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                permissions TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # API Usage log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id INTEGER NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (key_id) REFERENCES api_keys(key_id)
            )
        """)

        conn.commit()
        conn.close()

    def create_api_key(self, user_id: int, name: str,
                      permissions: list[str]) -> str:
        """
        Create a new API key.

        Returns:
            The generated API key (only shown once)
        """
        # Generate random API key
        api_key = f"sk_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        permissions_str = ','.join(permissions)
        cursor.execute("""
            INSERT INTO api_keys (user_id, key_hash, name, permissions)
            VALUES (?, ?, ?, ?)
        """, (user_id, key_hash, name, permissions_str))

        conn.commit()
        conn.close()

        return api_key

    def validate_api_key(self, api_key: str) -> APIKey | None:
        """Validate an API key and return associated data."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT key_id, user_id, key_hash, name, permissions, is_active,
                   created_at, last_used
            FROM api_keys
            WHERE key_hash = ? AND is_active = 1
        """, (key_hash,))

        row = cursor.fetchone()

        if row:
            # Update last used timestamp
            cursor.execute("""
                UPDATE api_keys SET last_used = CURRENT_TIMESTAMP
                WHERE key_id = ?
            """, (row[0],))
            conn.commit()

        conn.close()

        if row:
            return APIKey(*row)
        return None

    def revoke_api_key(self, key_id: int):
        """Revoke an API key."""
        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        cursor.execute("UPDATE api_keys SET is_active = 0 WHERE key_id = ?",
                      (key_id,))

        conn.commit()
        conn.close()

    def list_api_keys(self, user_id: int) -> list[APIKey]:
        """List all API keys for a user."""
        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT key_id, user_id, key_hash, name, permissions, is_active,
                   created_at, last_used
            FROM api_keys
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))

        keys = [APIKey(*row) for row in cursor.fetchall()]
        conn.close()
        return keys

    def log_api_usage(self, key_id: int, endpoint: str, method: str,
                     status_code: int, response_time_ms: int):
        """Log API usage."""
        conn = sqlite3.connect(str(self.api_db))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO api_usage (key_id, endpoint, method, status_code, response_time_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (key_id, endpoint, method, status_code, response_time_ms))

        conn.commit()
        conn.close()

    # ==================== API Endpoints ====================

    def get_plants(self, api_key: APIKey, filters: dict = None) -> dict:
        """
        API Endpoint: Get list of plants.

        Permissions required: read
        """
        if 'read' not in api_key.permissions:
            return {'error': 'Insufficient permissions', 'status': 403}

        try:
            conn = sqlite3.connect(str(self.toolkit_db))
            query = "SELECT * FROM plants"

            if filters:
                # Add basic filtering support
                where_clauses = []
                params = []
                for key, value in filters.items():
                    where_clauses.append(f"{key} = ?")
                    params.append(value)

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
                    df = pd.read_sql_query(query, conn, params=params)
                else:
                    df = pd.read_sql_query(query, conn)
            else:
                df = pd.read_sql_query(query, conn)

            conn.close()

            return {
                'status': 200,
                'data': df.to_dict('records'),
                'count': len(df)
            }
        except Exception as e:
            return {'error': str(e), 'status': 500}

    def get_plant_data(self, api_key: APIKey, plant_id: str,
                      start_date: str | None = None,
                      end_date: str | None = None) -> dict:
        """
        API Endpoint: Get data for a specific plant.

        Permissions required: read
        """
        if 'read' not in api_key.permissions:
            return {'error': 'Insufficient permissions', 'status': 403}

        try:
            conn = sqlite3.connect(str(self.toolkit_db))

            query = "SELECT * FROM plant_data WHERE plant_id = ?"
            params = [plant_id]

            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)

            query += " ORDER BY date"

            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            return {
                'status': 200,
                'plant_id': plant_id,
                'data': df.to_dict('records'),
                'count': len(df)
            }
        except Exception as e:
            return {'error': str(e), 'status': 500}

    def get_performance_metrics(self, api_key: APIKey,
                               plant_id: str | None = None,
                               metric_type: str | None = None) -> dict:
        """
        API Endpoint: Get performance metrics.

        Permissions required: read
        """
        if 'read' not in api_key.permissions:
            return {'error': 'Insufficient permissions', 'status': 403}

        try:
            conn = sqlite3.connect(str(self.reporting_db))

            query = "SELECT * FROM performance_metrics WHERE 1=1"
            params = []

            if plant_id:
                query += " AND plant_id = ?"
                params.append(plant_id)

            if metric_type:
                query += " AND metric_type = ?"
                params.append(metric_type)

            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            return {
                'status': 200,
                'data': df.to_dict('records'),
                'count': len(df)
            }
        except Exception as e:
            return {'error': str(e), 'status': 500}

    def get_alerts(self, api_key: APIKey, active_only: bool = True) -> dict:
        """
        API Endpoint: Get alert rules.

        Permissions required: read
        """
        if 'read' not in api_key.permissions:
            return {'error': 'Insufficient permissions', 'status': 403}

        try:
            from services.notification_service import NotificationService
            notif_service = NotificationService()

            alerts = notif_service.get_alerts(active_only=active_only)

            return {
                'status': 200,
                'data': [
                    {
                        'alert_id': a.alert_id,
                        'name': a.name,
                        'description': a.description,
                        'metric': a.metric,
                        'condition': a.condition,
                        'threshold': a.threshold,
                        'is_active': a.is_active,
                    }
                    for a in alerts
                ],
                'count': len(alerts)
            }
        except Exception as e:
            return {'error': str(e), 'status': 500}

    def create_export(self, api_key: APIKey, export_type: str,
                     params: dict) -> dict:
        """
        API Endpoint: Create a data export.

        Permissions required: export
        """
        if 'export' not in api_key.permissions:
            return {'error': 'Insufficient permissions', 'status': 403}

        try:
            from services.export_service import ExportFormat, ExportService

            export_service = ExportService()

            # Handle different export types
            if export_type == 'plant_summary':
                plant_id = params.get('plant_id')
                if not plant_id:
                    return {'error': 'plant_id required', 'status': 400}

                # Get plant data
                conn = sqlite3.connect(str(self.toolkit_db))
                df = pd.read_sql_query(
                    "SELECT * FROM plant_data WHERE plant_id = ?",
                    conn, params=[plant_id]
                )
                conn.close()

                format = params.get('format', ExportFormat.CSV)
                data = export_service.export_dataframe(df, f'plant_{plant_id}', format)

                return {
                    'status': 200,
                    'message': 'Export created successfully',
                    'data': data.decode() if format == ExportFormat.CSV else None,
                    'size_bytes': len(data)
                }

            else:
                return {'error': f'Unknown export type: {export_type}', 'status': 400}

        except Exception as e:
            return {'error': str(e), 'status': 500}


class APIDocumentation:
    """API Documentation and examples."""

    ENDPOINTS = {
        'GET /api/plants': {
            'description': 'List all plants',
            'permissions': ['read'],
            'parameters': {
                'filters': 'Optional dict of field:value filters'
            },
            'example': {
                'request': 'GET /api/plants?country=UK',
                'response': {
                    'status': 200,
                    'data': [{'plant_id': '1', 'name': 'Solar Farm A'}],
                    'count': 1
                }
            }
        },
        'GET /api/plants/{plant_id}': {
            'description': 'Get data for a specific plant',
            'permissions': ['read'],
            'parameters': {
                'plant_id': 'Plant identifier',
                'start_date': 'Optional start date (YYYY-MM-DD)',
                'end_date': 'Optional end date (YYYY-MM-DD)'
            }
        },
        'GET /api/metrics': {
            'description': 'Get performance metrics',
            'permissions': ['read'],
            'parameters': {
                'plant_id': 'Optional plant filter',
                'metric_type': 'Optional metric type filter'
            }
        },
        'GET /api/alerts': {
            'description': 'Get alert rules',
            'permissions': ['read'],
            'parameters': {
                'active_only': 'Boolean, default true'
            }
        },
        'POST /api/export': {
            'description': 'Create a data export',
            'permissions': ['export'],
            'parameters': {
                'export_type': 'Type of export (plant_summary, etc)',
                'params': 'Export-specific parameters',
                'format': 'csv, xlsx, json, or parquet'
            }
        }
    }

    @classmethod
    def get_openapi_spec(cls) -> dict:
        """Generate OpenAPI 3.0 specification."""
        return {
            'openapi': '3.0.0',
            'info': {
                'title': 'Solar Portfolio Manager API',
                'version': '1.0.0',
                'description': 'API for accessing solar plant data and analytics'
            },
            'servers': [
                {'url': 'http://localhost:8501/api', 'description': 'Local server'}
            ],
            'security': [
                {'ApiKeyAuth': []}
            ],
            'components': {
                'securitySchemes': {
                    'ApiKeyAuth': {
                        'type': 'apiKey',
                        'in': 'header',
                        'name': 'X-API-Key'
                    }
                }
            },
            'paths': cls.ENDPOINTS
        }
