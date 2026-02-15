# New Features Implementation

This document describes the newly implemented features for the Solar Portfolio Manager application.

## 🔐 Feature 1: Authentication & Multi-User (⭐⭐⭐)

### Overview
Complete user authentication system with role-based access control, user management, and audit logging.

### Components
- **Authentication Service** (`services/auth_service.py`)
  - User registration and login
  - Password hashing with SHA-256
  - Role-based permissions (admin, manager, analyst, viewer)
  - Session management
  - Audit logging

- **Authentication UI** (`components/auth_ui.py`)
  - Login page
  - User profile management
  - Password change functionality
  - User management interface (admin only)
  - Audit log viewer

### Features
- **4 User Roles:**
  - **Admin**: Full access including user management
  - **Manager**: Read, write, and export permissions
  - **Analyst**: Read, write, and export permissions
  - **Viewer**: Read-only access

- **Default Credentials:**
  - Username: `admin`
  - Password: `admin123`
  - **⚠️ Change this immediately in production!**

### Database
- User database: `~/.solar_toolkit/users.db`
- Tables: users, sessions, audit_log

### Usage
```python
from services.auth_service import require_login, require_permission, get_current_user

# Require login for a page
require_login()

# Check specific permission
require_permission("export")

# Get current user
user = get_current_user()
if user:
    print(f"Logged in as: {user.full_name}")
```

---

## 🔔 Feature 2: Alerts & Notifications (⭐⭐⭐)

### Overview
Comprehensive notification system with threshold-based alerts, notification center, and alert management.

### Components
- **Notification Service** (`services/notification_service.py`)
  - Create and manage notifications
  - Define alert rules with thresholds
  - Alert history tracking
  - Notification delivery

- **Notifications UI** (`components/notifications_ui.py`)
  - Notification center
  - Alert management interface
  - Notification badge in sidebar
  - Toast notifications

### Features
- **Notification Types:**
  - Info
  - Warning
  - Error
  - Success
  - Alert

- **Pre-configured Alerts:**
  - Low PR Alert (PR < 75%)
  - High Availability (>99%)
  - Low Availability (<95%)
  - High Clipping Loss (>5%)
  - High Soiling Loss (>3%)

- **Alert Conditions:**
  - Less than (<)
  - Greater than (>)
  - Less than or equal (<=)
  - Greater than or equal (>=)
  - Equal to (==)
  - Not equal to (!=)

### Database
- Notifications database: `~/.solar_toolkit/notifications.db`
- Tables: notifications, alerts, alert_history

### Usage
```python
from services.notification_service import get_notification_service

service = get_notification_service()

# Create a notification
service.create_notification(
    user_id=1,
    title="Low Performance",
    message="Plant A has PR below 70%",
    notification_type="warning"
)

# Check alert thresholds
service.check_alert("pr", 72.5, user_id=1)

# Create custom alert
service.create_alert(
    name="Custom Alert",
    description="Monitor custom metric",
    metric="custom_metric",
    condition=">",
    threshold=100.0
)
```

---

## 📤 Feature 3: Data Export & API (⭐⭐)

### Overview
Flexible data export system with multiple formats and RESTful API for programmatic access.

### Components

#### Data Export
- **Export Service** (`services/export_service.py`)
  - Export to multiple formats: CSV, Excel, JSON, Parquet
  - Multi-sheet Excel exports
  - Zip package creation
  - Export templates
  - Export history and cleanup

- **Export UI** (`modules/data_export_ui.py`)
  - Quick export templates
  - Custom export builder
  - Scheduled exports (coming soon)
  - Export history viewer

#### API
- **API Service** (`services/api_service.py`)
  - API key management
  - RESTful endpoints
  - Usage logging
  - OpenAPI documentation

- **API Management UI** (`modules/api_management_ui.py`)
  - API key creation and management
  - API documentation viewer
  - Usage statistics
  - Interactive testing console

### Export Formats
- **CSV**: Comma-separated values
- **Excel (.xlsx)**: Multi-sheet workbooks
- **JSON**: Structured JSON data
- **Parquet**: Columnar storage format

### API Endpoints
```
GET  /api/plants              - List all plants
GET  /api/plants/{id}         - Get plant data
GET  /api/metrics             - Get performance metrics
GET  /api/alerts              - Get alert rules
POST /api/export              - Create data export
```

### API Authentication
All API requests require an API key in the `X-API-Key` header:

```python
import requests

headers = {"X-API-Key": "sk_your_api_key_here"}
response = requests.get("http://localhost:8501/api/plants", headers=headers)
print(response.json())
```

### Export Examples

#### Quick Export
```python
from services.export_service import ExportService, ExportFormat

service = ExportService()

# Export DataFrame to Excel
data = service.export_dataframe(df, "my_export", ExportFormat.EXCEL)

# Export multiple sheets
sheets = {
    "Sheet1": df1,
    "Sheet2": df2,
}
data = service.export_multiple_sheets(sheets, "multi_sheet_export")
```

#### Template Exports
```python
from services.export_service import TemplateExports

# Monthly performance report
sheets = TemplateExports.monthly_performance_report(db_path, 2024, 3)

# Plant summary report
sheets = TemplateExports.plant_summary_report(db_path, "PLANT001")
```

---

## 📊 Feature 4: Comparative Analysis Dashboard (⭐⭐)

### Overview
Advanced analytics dashboard for comparing plants, time periods, and metrics side-by-side.

### Components
- **Comparative Analysis Module** (`modules/comparative_analysis.py`)
  - Plant comparison
  - Time period comparison
  - Metric comparison
  - Portfolio overview

### Analysis Types

#### 1. Plant Comparison
- Compare up to 5 plants simultaneously
- Side-by-side KPI metrics
- Energy production trends
- Performance ratio distribution
- Availability comparison
- Loss analysis

#### 2. Time Period Comparison
- Compare same plant across different periods
- Period-over-period changes
- Trend analysis
- Statistical comparison

#### 3. Metric Comparison
- Compare specific metrics across all plants
- Plant rankings
- Distribution analysis
- Statistical summaries

#### 4. Portfolio Overview
- Portfolio-wide KPIs
- Geographic distribution
- Performance distribution
- Top and bottom performers

### Visualizations
- Line charts for trends
- Box plots for distributions
- Bar charts for comparisons
- Pie charts for composition
- Multi-panel dashboards

### Usage
1. Navigate to **Advanced > Comparative Analysis**
2. Select analysis type
3. Choose plants/periods/metrics to compare
4. View interactive visualizations and statistics

---

## 🚀 Getting Started

### Installation

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

New dependencies include:
- `pyarrow>=14.0.0` - Parquet export
- `fastparquet>=2023.10.0` - Alternative parquet engine
- `cryptography>=41.0.0` - Secure password hashing
- `PyJWT>=2.8.0` - JWT tokens
- `python-dateutil>=2.8.0` - Date utilities
- `pytz>=2023.3` - Timezone support

2. **Run the Application**
```bash
streamlit run app.py
```

3. **First-Time Setup**
- Log in with default credentials: `admin` / `admin123`
- Navigate to **User Management** to create additional users
- Change the admin password immediately

### Quick Tour

1. **Authentication**
   - Log in with your credentials
   - Access user menu from sidebar
   - View profile and change password

2. **Notifications**
   - Check notification badge in sidebar
   - Navigate to **Notifications** to view all
   - Manage alert rules in the Alerts tab

3. **Data Export**
   - Navigate to **Advanced > Data Export**
   - Use quick templates or build custom exports
   - Download in your preferred format

4. **API Access**
   - Navigate to **Advanced > API Management**
   - Create an API key with required permissions
   - Use the API documentation for integration

5. **Comparative Analysis**
   - Navigate to **Advanced > Comparative Analysis**
   - Select analysis type
   - Compare plants, periods, or metrics

---

## 📁 File Structure

```
unified_app/
├── services/
│   ├── auth_service.py           # Authentication service
│   ├── notification_service.py   # Notifications and alerts
│   ├── export_service.py         # Data export functionality
│   └── api_service.py            # API endpoints and management
│
├── components/
│   ├── auth_ui.py                # Authentication UI components
│   └── notifications_ui.py       # Notification UI components
│
├── modules/
│   ├── comparative_analysis.py   # Comparative analysis dashboard
│   ├── data_export_ui.py         # Data export interface
│   └── api_management_ui.py      # API management interface
│
├── app.py                        # Main application (updated)
├── components/sidebar.py         # Sidebar (updated)
└── requirements.txt              # Dependencies (updated)
```

---

## 🔒 Security Considerations

1. **Change Default Password**
   - The default admin password is `admin123`
   - Change this immediately after first login

2. **API Keys**
   - Store API keys securely
   - Never commit API keys to version control
   - Rotate keys regularly
   - Use minimum required permissions

3. **Database Security**
   - User database is stored in `~/.solar_toolkit/users.db`
   - Ensure proper file permissions
   - Back up databases regularly

4. **Password Requirements**
   - Minimum 8 characters
   - Consider implementing stronger requirements for production

---

## 🎯 Best Practices

### User Management
- Create separate accounts for each user
- Use appropriate roles based on responsibilities
- Review audit logs regularly
- Deactivate users when they leave

### Notifications
- Configure alerts for critical metrics
- Set appropriate thresholds
- Review alert history to tune thresholds
- Use notifications for important system events

### Data Export
- Use templates for common exports
- Clean up old exports regularly (30+ days)
- Use appropriate formats (Parquet for large datasets)
- Schedule regular exports for reporting

### API Usage
- Create separate API keys for different integrations
- Use descriptive names for API keys
- Monitor API usage statistics
- Revoke unused keys

---

## 🐛 Troubleshooting

### Authentication Issues
- **Can't log in**: Verify username and password
- **Database errors**: Check if `~/.solar_toolkit/users.db` exists
- **Permission denied**: Contact admin to assign proper role

### Notification Issues
- **Alerts not triggering**: Check alert is active and threshold is correct
- **No notifications**: Verify notification service is initialized

### Export Issues
- **Export fails**: Check database connection and query
- **Large exports timeout**: Use Parquet format or limit data
- **File not found**: Check export directory permissions

### API Issues
- **401 Unauthorized**: Verify API key is correct and active
- **403 Forbidden**: Check API key has required permissions
- **500 Server Error**: Check server logs for details

---

## 📝 Future Enhancements

- Email notifications for alerts
- Scheduled exports with email delivery
- Advanced API rate limiting
- Two-factor authentication
- SSO integration
- Real-time dashboards
- Mobile app support
- Advanced analytics and ML predictions

---

## 📞 Support

For issues, questions, or feature requests:
1. Check this documentation
2. Review the code comments
3. Contact your system administrator
4. Open an issue in the project repository

---

## 📜 License

Copyright © 2024 AMPYR Solar Portfolio Manager
All rights reserved.
