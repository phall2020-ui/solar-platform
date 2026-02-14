# Installation & Testing Guide

## 📦 Installation

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

New packages installed:
- `pyarrow` - For Parquet export format
- `fastparquet` - Alternative Parquet engine
- `cryptography` - Secure password hashing
- `PyJWT` - JWT token support
- `python-dateutil` - Date utilities
- `pytz` - Timezone support

### Step 2: Run the Application

```bash
streamlit run app.py
```

The application will start and open in your browser at `http://localhost:8501`

---

## 🔐 First-Time Setup

### 1. Login

**Default Credentials:**
- Username: `admin`
- Password: `admin123`

⚠️ **IMPORTANT:** Change this password immediately after first login!

### 2. Change Admin Password

1. Click on your username in the sidebar
2. Click "Profile"
3. Use the "Change Password" form
4. Enter current password: `admin123`
5. Enter and confirm new password (min 8 characters)
6. Click "Update Password"

### 3. Create Additional Users

1. Navigate to "User Management" (admin only)
2. Go to "Add User" tab
3. Fill in user details:
   - Username (unique)
   - Email (unique)
   - Full Name
   - Password (min 8 characters)
   - Role (viewer, analyst, manager, or admin)
4. Click "Create User"

---

## 🧪 Testing Guide

### Test 1: Authentication & User Management

**Test Login:**
- [ ] Log in with admin credentials
- [ ] View user profile
- [ ] Change password
- [ ] Logout and login with new password

**Test User Management (Admin only):**
- [ ] Create a new user (viewer role)
- [ ] View user list
- [ ] Update user role
- [ ] Deactivate user
- [ ] View audit log

**Expected Results:**
- Login successful with correct credentials
- Password change works
- New users can login
- Audit log shows all actions
- Deactivated users cannot login

---

### Test 2: Alerts & Notifications

**Test Notification Center:**
1. Navigate to **Advanced > Notifications**
2. [ ] View all notifications
3. [ ] Mark notification as read
4. [ ] Delete notification
5. [ ] Mark all as read

**Test Alert Management:**
1. Go to "Alerts" tab
2. [ ] View existing alert rules
3. [ ] Create new alert:
   - Name: "Test Alert"
   - Metric: "pr"
   - Condition: "<"
   - Threshold: 80
4. [ ] Edit existing alert
5. [ ] Deactivate alert
6. [ ] View alert history

**Test Alert Triggering:**
```python
# This would typically happen automatically during data processing
from services.notification_service import get_notification_service

service = get_notification_service()
service.check_alert("pr", 75.5, user_id=1)  # Should trigger if threshold < 80
```

**Expected Results:**
- Notifications appear in center
- Read/unread status works
- Alerts can be created and edited
- Alert history shows triggered alerts
- Notification badge shows unread count

---

### Test 3: Data Export

**Test Quick Export:**
1. Navigate to **Advanced > Data Export**
2. [ ] Export Monthly Performance Report
   - Select year and month
   - Click "Export Monthly Report"
   - Download Excel file
3. [ ] Export Plant Summary
   - Select a plant
   - Click "Export Plant Summary"
   - Download Excel file

**Test Custom Export:**
1. Go to "Custom Export" tab
2. [ ] Build custom export:
   - Name: "Test Export"
   - Data source: "Solar Toolkit"
   - Table: "plants"
   - Format: Excel
3. [ ] Try different formats (CSV, JSON, Parquet)
4. [ ] Add date filters
5. [ ] Download exports

**Test Export History:**
1. Go to "Export History" tab
2. [ ] View exported files
3. [ ] Filter by format
4. [ ] Sort by date/size
5. [ ] Cleanup old exports (test with 7 days)

**Expected Results:**
- Templates generate multi-sheet Excel files
- Custom exports work for all formats
- Downloads complete successfully
- Export history shows all exports
- Cleanup removes old files

---

### Test 4: API Management

**Test API Key Creation:**
1. Navigate to **Advanced > API Management**
2. [ ] Create API key:
   - Name: "Test Integration"
   - Permissions: Read, Export
3. [ ] Copy API key (shown once!)
4. [ ] View API key in list
5. [ ] Test API key status

**Test API Documentation:**
1. Go to "Documentation" tab
2. [ ] View all endpoints
3. [ ] Read endpoint details
4. [ ] Download OpenAPI spec

**Test API Endpoints:**

Using curl or Python:

```bash
# Set your API key
API_KEY="sk_your_key_here"

# Test GET /api/plants
curl -H "X-API-Key: $API_KEY" http://localhost:8501/api/plants
```

Or with Python:
```python
import requests

headers = {"X-API-Key": "sk_your_key_here"}

# Get plants
response = requests.get("http://localhost:8501/api/plants", headers=headers)
print(response.json())

# Get specific plant data
response = requests.get(
    "http://localhost:8501/api/plants/PLANT001",
    headers=headers,
    params={"start_date": "2024-01-01", "end_date": "2024-01-31"}
)
print(response.json())
```

**Test API Key Management:**
1. [ ] Create multiple API keys
2. [ ] Revoke an API key
3. [ ] Try using revoked key (should fail)
4. [ ] View usage statistics

**Expected Results:**
- API keys are generated successfully
- Keys shown only once (security)
- API endpoints respond correctly
- Revoked keys return 403 error
- Documentation is complete and accurate

---

### Test 5: Comparative Analysis

**Test Plant Comparison:**
1. Navigate to **Advanced > Comparative Analysis**
2. [ ] Select "Plant Comparison"
3. [ ] Select 2-5 plants
4. [ ] Choose time period (Last 30 Days)
5. [ ] View KPI metrics
6. [ ] Explore all visualization tabs:
   - Energy Production
   - Performance Ratio
   - Availability
   - Loss Analysis
7. [ ] Review summary statistics

**Test Time Period Comparison:**
1. [ ] Select "Time Period Comparison"
2. [ ] Select a plant
3. [ ] Choose two different periods
4. [ ] Compare metrics side-by-side
5. [ ] View change analysis
6. [ ] Review trend charts

**Test Metric Comparison:**
1. [ ] Select "Metric Comparison"
2. [ ] Choose a metric (e.g., Performance Ratio)
3. [ ] Select time period
4. [ ] View plant rankings
5. [ ] Analyze distribution
6. [ ] Review statistical summary

**Test Portfolio Overview:**
1. [ ] Select "Portfolio Overview"
2. [ ] View portfolio KPIs
3. [ ] Check geographic distribution
4. [ ] Review performance distribution
5. [ ] See top performers
6. [ ] Identify plants needing attention

**Expected Results:**
- All visualizations render correctly
- Data is accurate and up-to-date
- Charts are interactive
- Statistics are calculated correctly
- Comparisons are meaningful

---

## 🎯 Feature Checklist

### Authentication & Multi-User ✅
- [x] User login/logout
- [x] Password management
- [x] User creation
- [x] Role-based permissions
- [x] User management (admin)
- [x] Audit logging
- [x] Session management

### Alerts & Notifications ✅
- [x] Notification center
- [x] Create/read/delete notifications
- [x] Alert rule management
- [x] Alert thresholds
- [x] Alert history
- [x] Notification badge
- [x] 5 pre-configured alerts

### Data Export & API ✅
- [x] CSV export
- [x] Excel export
- [x] JSON export
- [x] Parquet export
- [x] Quick templates
- [x] Custom exports
- [x] Export history
- [x] API key management
- [x] REST API endpoints
- [x] OpenAPI documentation

### Comparative Analysis ✅
- [x] Plant comparison
- [x] Time period comparison
- [x] Metric comparison
- [x] Portfolio overview
- [x] Interactive charts
- [x] Statistical analysis

---

## 📊 Performance Verification

### Database Files Created
Check that these files exist:
- `~/.solar_toolkit/users.db` (User database)
- `~/.solar_toolkit/notifications.db` (Notifications)
- `~/.solar_toolkit/api.db` (API keys)
- `~/.solar_toolkit/exports/` (Export directory)

### UI Navigation
Verify all new pages are accessible:
- [ ] Advanced > Comparative Analysis
- [ ] Advanced > Data Export
- [ ] Advanced > API Management
- [ ] Advanced > Notifications
- [ ] User Management (admin only)
- [ ] User Profile

---

## 🐛 Common Issues & Solutions

### Issue: Cannot log in
**Solution:**
- Verify username and password
- Check `~/.solar_toolkit/users.db` exists
- Try default credentials: admin/admin123

### Issue: No notifications appearing
**Solution:**
- Check notification service is initialized
- Verify alerts are active
- Check user_id is correct

### Issue: Export fails
**Solution:**
- Verify database connection
- Check table/query is valid
- Ensure export directory is writable

### Issue: API key not working
**Solution:**
- Verify key is active (not revoked)
- Check header format: `X-API-Key: sk_...`
- Confirm permissions match endpoint requirements

### Issue: Charts not loading
**Solution:**
- Check data exists for selected period/plants
- Verify database queries return data
- Clear browser cache

---

## 🔒 Security Checklist

Before deploying to production:

- [ ] Change default admin password
- [ ] Create individual user accounts
- [ ] Assign appropriate roles
- [ ] Review and adjust alert thresholds
- [ ] Secure API keys
- [ ] Set proper database file permissions
- [ ] Enable HTTPS for API access
- [ ] Implement rate limiting (production)
- [ ] Regular security audits
- [ ] Backup databases regularly

---

## 📞 Support

If you encounter issues:

1. Check this guide
2. Review `NEW_FEATURES.md` for detailed documentation
3. Check console/logs for error messages
4. Verify all dependencies are installed
5. Restart the application
6. Contact support with:
   - Error message
   - Steps to reproduce
   - Browser/environment details

---

## ✅ Installation Complete!

Once all tests pass, your Solar Portfolio Manager is ready with:

1. ✅ **Authentication & Multi-User** - Secure access control
2. ✅ **Alerts & Notifications** - Proactive monitoring
3. ✅ **Data Export & API** - Flexible data access
4. ✅ **Comparative Analysis** - Advanced insights

Enjoy your enhanced Solar Portfolio Manager! 🌞
