# AMPYR Solar Portfolio Manager — User Guide

> **Version 1.1.0** | Last updated: February 2026

Welcome to the AMPYR Solar Portfolio Manager — a unified Streamlit-based platform for monitoring, analysing, and reporting on your solar PV portfolio. This guide covers every feature available to end users.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Portfolio Overview](#portfolio-overview)
3. [Plant Detail](#plant-detail)
4. [Analysis Tools](#analysis-tools)
5. [Reports](#reports)
6. [Alerts & Tickets](#alerts--tickets)
7. [Financial Overview](#financial-overview)
8. [Data Management](#data-management)
9. [Settings](#settings)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Logging In

When you first open the application, you will be presented with a login screen.

1. Enter your **username** and **password**.
2. Click **Login**.
3. If your account is locked after 5 failed attempts, wait 15 minutes before retrying.

> **Tip:** Your administrator will provide your initial credentials. Change your password immediately after your first login via **Settings → Change Password**.

![Login Screen](images/login.png)

### User Roles

Your experience is tailored to your assigned role:

| Role | Permissions | Accessible Sections |
|------|-------------|---------------------|
| **Viewer** | Read-only access | Dashboard, Site Monitor, Data Overview, Settings |
| **Engineer** | Read + write + export | All analysis tools, reporting, data management, alerts |
| **Manager** | Read + write + export | Everything engineers can access plus Financial and Plant Management |
| **Admin** | Full access | All features including System Health, Database Viewer, API Management, User Management |

### Navigation Overview

The application uses a sidebar for navigation, organised into six groups:

| Group | Icon | Pages |
|-------|------|-------|
| **Portfolio** | 🏠 | Dashboard, Site Monitor, Data Overview |
| **Analysis** | 🔬 | Clipping, Curtailment, Shading, Fouling, Thermal Loss, Waterfall, Comparative, Anomaly Detection, PR Trending, Degradation |
| **Reporting** | 📝 | Monthly Performance, Report Builder, Report Library |
| **Financial** | 💰 | Financial Dashboard, Tariff Management |
| **Data Management** | 🗄️ | Data Explorer, Plant Management, POA Import, Data Export |
| **Admin** | ⚙️ | Data Quality, Alerts Dashboard, Ticket Kanban, System Health, Database Viewer, API Management |

Click any page name in the sidebar to navigate. The currently active page is highlighted.

![Sidebar Navigation](images/sidebar.png)

### Dashboard Walkthrough

The **Dashboard** is your landing page after login. It provides a fleet-level summary at a glance.

![Dashboard](images/dashboard.png)

**Key elements:**

1. **Time Range Selector** — Filter data by Last 24 Hours, Last 7 Days, Last 30 Days, Month to Date, or Year to Date.
2. **KPI Row** — Four headline metrics across the top (see [Understanding KPI Cards](#understanding-kpi-cards)).
3. **Plant Status Grid** — Every plant shown as a card with status indicators.
4. **Generation Trend Chart** — Portfolio-level generation over the selected period.
5. **Alert Summary** — Recent alerts requiring attention.

---

## Portfolio Overview

### Understanding KPI Cards

The KPI row at the top of the Dashboard displays four headline metrics:

| KPI | Description | Status Indicator |
|-----|-------------|------------------|
| **Total Capacity** | Sum of all registered plant capacities in MWp, with plant count | Always neutral |
| **Total Generation** | Aggregate energy produced in MWh for the selected period | Green if trending up; amber if down |
| **Average PR** | Fleet-wide Performance Ratio as a percentage | Green ≥ 85%, amber 70–85%, red < 70% |
| **Fleet Availability** | Percentage of plants reporting data normally | Green ≥ 95%, amber 90–95%, red < 90% |

Each KPI card also shows a delta — the percentage change compared to the prior equivalent period.

> **Tip:** Hover over a KPI card for additional context. Click the card area to drill down where supported.

### Plant Status Indicators

Each plant in the status grid displays a coloured indicator:

| Colour | Status | Meaning |
|--------|--------|---------|
| 🟢 Green | **Excellent** | PR > 85% — performing as expected |
| 🔵 Teal | **Good** | PR 70–85% — within acceptable range |
| 🟡 Amber | **Warning** | PR 50–70% — investigation recommended |
| 🔴 Red | **Critical** | PR < 50% — immediate attention required |
| ⚪ Grey | **Offline** | No data received in the evaluation window |

Click any plant card to navigate to its **Plant Detail** page.

### Portfolio Map View

The **Site Monitor** page (📡) displays all plants on an interactive map, colour-coded by status. Use this to quickly identify geographical clusters of underperformance.

- **Zoom** — Scroll or pinch to zoom in/out.
- **Click a marker** — View plant name, capacity, and current PR.
- **Filter** — Use the status filter to show only plants of a specific status.

![Portfolio Map](images/portfolio_map.png)

### Data Overview

The **Data Overview** page (📋) provides a summary of all available data across the portfolio:

- Date ranges covered per plant
- Row counts and data completeness
- Last data refresh timestamps

---

## Plant Detail

Access the Plant Detail page by clicking any plant on the Dashboard or Site Monitor.

![Plant Detail](images/plant_detail.png)

### Performance Metrics

The Plant Detail page shows metrics specific to a single plant:

| Metric | Description |
|--------|-------------|
| **Performance Ratio (PR)** | Ratio of actual vs. expected energy output, expressed as a percentage |
| **Specific Yield** | kWh generated per kWp of installed capacity |
| **Availability** | Percentage of time the plant was operational |
| **Capacity Factor** | Ratio of actual output to theoretical maximum |

### Generation Charts

Interactive Plotly charts display:

- **Daily generation** (bar chart) with POA irradiance overlay
- **Hourly generation profile** for selected dates
- **Monthly generation vs. budget** comparison

Use the time range selector to adjust the view. Charts can be zoomed, panned, and exported as PNG images using the Plotly toolbar.

### PR Analysis

The PR section breaks down performance ratio over time:

- **PR trend line** with rolling average
- **PR vs. irradiance** scatter plot to identify weather-correlated patterns
- **PR heatmap** showing hourly performance patterns

---

## Analysis Tools

All analysis pages in the **Analysis** group (🔬) require a plant to be selected. Use the plant selector dropdown at the top of each page.

### Comparative Analysis

📈 **Cross-plant performance comparison**

Compare multiple plants side-by-side across key metrics:

1. Select two or more plants from the multi-select dropdown.
2. Choose the comparison metric (PR, Generation, Availability, Specific Yield).
3. Set the date range.
4. View the comparison chart and ranking table.

This is useful for identifying outliers and benchmarking plant performance across the fleet.

![Comparative Analysis](images/comparative_analysis.png)

### Clipping Analysis

✂️ **Inverter clipping detection with configurable thresholds**

Identifies periods when inverter output is capped at its rated capacity, causing energy loss.

**How to use:**

1. Select a plant.
2. Set the **clipping threshold** — the percentage of rated capacity above which output is considered clipped (default: 95%).
3. View the clipping profile chart showing actual output vs. capacity limit.
4. Review the summary table with estimated clipping losses in kWh and percentage.

**Key outputs:**

| Output | Description |
|--------|-------------|
| Clipping Events | Number of intervals where clipping was detected |
| Estimated Loss (kWh) | Energy lost due to inverter power limiting |
| Clipping Percentage | Proportion of total generation lost to clipping |

> **Tip:** Consistently high clipping may indicate the plant could benefit from inverter upsizing or DC/AC ratio adjustment.

### Curtailment Analysis

⚡ **Export limitation detection and loss estimation**

Detects periods when plant output was curtailed due to grid export limits or network operator instructions.

**How to use:**

1. Select a plant with configured export limits.
2. View the curtailment timeline showing periods of constrained output.
3. Review estimated energy loss and revenue impact.

The analysis compares actual output against the modelled potential output (based on irradiance) to quantify curtailment losses.

### Shading Analysis

🌤️ **Hourly performance profile for shade detection**

Identifies near-shading losses by comparing performance during baseline months (typically summer: June–August) against comparison months (typically winter: October–December).

**How to use:**

1. Select a plant.
2. Configure baseline months (high sun angle, no shading expected).
3. Configure comparison months (low sun angle, shading possible).
4. View the hourly performance profile — dips during specific hours indicate shading.

The output includes a heatmap showing hourly PR by month, making seasonal shading patterns clearly visible.

![Shading Analysis](images/shading_analysis.png)

### Fouling Analysis

🧹 **Soiling trend detection**

Tracks gradual performance decline due to panel soiling (dust, pollen, bird droppings) and identifies cleaning events.

**How to use:**

1. Select a plant.
2. Set the **clean days threshold** — number of days after rain/cleaning that panels are considered clean (default: 3 days).
3. View the soiling trend showing normalised PR decline between cleaning events.
4. Review estimated soiling losses.

> **Tip:** If soiling losses exceed 2%, consider increasing cleaning frequency or installing anti-soiling coatings.

### Thermal Loss

🌡️ **Temperature coefficient analysis**

Quantifies energy losses due to module operating temperatures exceeding the standard test conditions (STC) reference of 25°C.

**How to use:**

1. Select a plant.
2. View the temperature coefficient regression (PR vs. module temperature).
3. Review monthly thermal loss estimates.

**Typical outputs:**

- Temperature coefficient (typically -0.3% to -0.5% per °C for crystalline silicon)
- Annual thermal loss estimate as a percentage
- Monthly breakdown of thermal derating

### Loss Waterfall

💧 **IEC 61724 loss breakdown across all categories**

Provides a comprehensive waterfall chart decomposing the gap between reference yield and final yield into individual loss categories.

**Loss categories (in order):**

1. **Reference Yield** — Energy expected at STC
2. **Temperature Loss** — Thermal derating
3. **Soiling Loss** — Panel fouling
4. **Shading Loss** — Near and far shading
5. **Clipping Loss** — Inverter power limiting
6. **Curtailment Loss** — Grid export limitation
7. **Availability Loss** — Downtime (plant or grid)
8. **Other Losses** — Cable, transformer, mismatch
9. **Final Yield** — Actual energy delivered

![Loss Waterfall](images/loss_waterfall.png)

> **Tip:** Use this chart for O&M reporting and identifying the dominant loss category for each plant.

### PR Trending

📉 **Performance Ratio trend tracking with rolling averages**

Tracks PR over time with configurable rolling average windows to smooth weather-related variability and reveal underlying trends.

**How to use:**

1. Select a plant.
2. Choose the rolling average window (7, 14, 30, or 90 days).
3. View the PR trend with confidence bands.
4. Compare against the budget PR target (default: 79%).

### Degradation Analysis

🪫 **Long-term PR degradation estimation**

Estimates the annual rate of PR decline, which indicates module aging and long-term performance loss.

**How to use:**

1. Select a plant with at least 12 months of historical data.
2. View the degradation regression line fitted to monthly PR values.
3. Review the estimated annual degradation rate (typically 0.3–0.8% per year for crystalline silicon).
4. Compare against the PVsyst or financial model assumption.

> **Tip:** Degradation rates significantly above the expected range may indicate accelerated aging, quality issues, or persistent soiling.

### Anomaly Detection

🔍 **Detect anomalous plant behaviour**

Uses statistical methods to flag unusual performance patterns that may indicate equipment faults, data issues, or external factors.

---

## Reports

### Monthly Performance Report

📅 Navigate to **Reporting → Monthly Performance** to generate monthly reports.

**Steps:**

1. Select the reporting month and year.
2. Choose the plants to include (individual or all).
3. Click **Generate Report**.
4. Review the report preview on-screen.
5. Download as PDF or add to the Report Library.

**Report contents include:**

- Executive summary with fleet KPIs
- Plant-by-plant performance tables
- Generation vs. budget charts
- Loss breakdown analysis
- Availability statistics

### Report Builder

📄 The **Report Builder** provides template-driven PDF report generation.

**Available templates:**

| Template | Description |
|----------|-------------|
| **Monthly Performance** | Standard monthly report with KPIs and charts |
| **ExCom Report** | Executive committee summary for stakeholder reporting |
| **O&M Report** | Operations and maintenance report with ticket summaries |

**How to use:**

1. Select a report template.
2. Configure the report parameters (date range, plants, sections to include).
3. Preview the report layout.
4. Generate and download the PDF.

### Report Library

📚 The **Report Library** stores all previously generated reports for browsing and downloading.

- Browse reports by date, type, and plant.
- Download reports in PDF format.
- Delete old reports to free storage.

> **Tip:** Reports are stored in the `reports/` directory. Ensure adequate disk space on the server.

---

## Alerts & Tickets

### Alert Rules

The system includes 12 pre-configured alert rules that continuously evaluate plant performance:

| Rule | Metric | Condition | Threshold | Severity | Auto-Ticket |
|------|--------|-----------|-----------|----------|-------------|
| Low PR | `pr` | Below | 75% | ⚠️ Warning | Yes (High) |
| Critical Low PR | `pr` | Below | 65% | 🔴 Critical | Yes (Critical) |
| Low Availability | `availability_pct` | Below | 95% | ⚠️ Warning | Yes (Medium) |
| Comms Gap | `comms_gap_minutes` | Above | 60 min | 🔴 Critical | Yes (High) |
| Clipping Loss High | `clipping_loss_pct` | Above | 3% | ⚠️ Warning | No |
| Curtailment High | `curtailment_rate_pct` | Above | 5% | ⚠️ Warning | No |
| Fouling Loss High | `fouling_loss_pct` | Above | 2% | ⚠️ Warning | No |
| Thermal Loss High | `thermal_loss_pct` | Above | 4% | ⚠️ Warning | No |
| High Module Temp | `module_temp_c` | Above | 70°C | ⚠️ Warning | No |
| No Data | `no_data` | No Data | — | 🔴 Critical | Yes (Critical) |
| Data Quality Low | `data_quality_score` | Below | 0.8 | ⚠️ Warning | No |
| Power Spike | `power_kw` | Above | 15,000 kW | ℹ️ Info | No |

### Alert Severity Levels

| Level | Icon | Meaning |
|-------|------|---------|
| **Info** | ℹ️ | Informational — no action required |
| **Warning** | ⚠️ | Investigate when convenient — may indicate developing issue |
| **Critical** | 🔴 | Immediate attention required — significant performance impact |

### Alert Lifecycle

Alerts follow a three-stage lifecycle:

```
┌──────────┐    ┌──────────────┐    ┌──────────┐
│   New    │───▶│ Acknowledged │───▶│ Resolved │
└──────────┘    └──────────────┘    └──────────┘
```

1. **New** — Alert has been triggered and is awaiting review.
2. **Acknowledged** — An operator has seen the alert and is investigating.
3. **Resolved** — The underlying condition has been addressed.

Navigate to **Admin → Alerts Dashboard** (🚨) to view and manage alerts. Use the **Evaluate Rules** button to trigger an immediate evaluation of all rules across the fleet.

### Ticket Kanban Board

Critical alerts with `auto_create_ticket` enabled automatically generate operational tickets. All tickets are managed on the **Ticket Kanban** board (🧩).

**Ticket workflow:**

```
┌──────┐   ┌─────────────┐   ┌─────────┐   ┌──────────┐   ┌────────┐
│ Open │──▶│ In Progress │──▶│ Blocked │──▶│ Resolved │──▶│ Closed │
└──────┘   └─────────────┘   └─────────┘   └──────────┘   └────────┘
```

**Key actions:**

- **Move tickets** between columns using the status dropdown on each card.
- **Assign tickets** to team members.
- **View ticket details** including the originating alert, plant, and priority.

> **Tip:** Use the Kanban board during daily stand-ups to review open tickets and track progress.

---

## Financial Overview

### Financial Dashboard

💷 Navigate to **Financial → Financial Dashboard** for revenue and budget tracking.

**Key features:**

- **Revenue summary** — Total revenue across the portfolio with period comparison.
- **Budget vs. Actual** — Chart comparing actual generation revenue against budget projections.
- **Plant revenue ranking** — Sorted list of plants by revenue contribution.
- **Tariff rate overview** — Current tariff rates applied to each plant.

![Financial Dashboard](images/financial_dashboard.png)

### Tariff Management

📋 Navigate to **Financial → Tariff Management** to configure electricity tariff schedules.

**Features:**

- **Create** new tariff records with rate, currency, start/end dates.
- **Edit** existing tariffs.
- **Delete** outdated tariff entries.
- **Import tariffs from CSV** — Bulk upload tariff schedules using a CSV template.

**CSV import format:**

```csv
plant_uid,tariff_name,rate,currency,start_date,end_date
PLANT001,FiT 2024,0.0532,GBP,2024-01-01,2024-12-31
PLANT002,PPA Q1,0.0650,GBP,2024-01-01,2024-03-31
```

> **Tip:** Ensure tariff records cover all reporting periods. Gaps in tariff data will result in zero revenue calculations for those periods.

---

## Data Management

### Data Explorer

🔍 Navigate to **Data Management → Data Explorer** to browse raw plant data stored in the database.

**Features:**

- Select a database table from the dropdown.
- Filter by plant, date range, and specific columns.
- Sort by any column.
- View row counts and data statistics.
- Export filtered results to CSV.

> **Tip:** Use the Data Explorer to verify data imports and investigate anomalies spotted in analysis tools.

### Plant Management

🏗️ Navigate to **Data Management → Plant Management** to register and configure plants.

**Actions:**

- **Register** a new plant with name, capacity (kWp), location, API source, and device ID.
- **Edit** plant configuration (capacity, coordinates, export limit, etc.).
- **Fetch data** — Trigger a manual data pull from the configured API adapter.
- **View** plant metadata and registration details.

### POA Import

📥 Navigate to **Data Management → POA Import** to upload irradiance data.

**Supported formats:**

- SolarGIS CSV exports
- Custom irradiance CSV files with timestamp and POA columns

**Steps:**

1. Select the target plant.
2. Upload the CSV file.
3. Map columns to the expected fields (timestamp, POA irradiance).
4. Click **Import** to load the data into the database.

### Data Quality Dashboard

🏥 Navigate to **Admin → Data Quality** for data completeness and quality scoring.

**Features:**

- **Quality score** per plant — A composite score (0.0–1.0) assessing completeness, consistency, and freshness.
- **Gap detection** — Identifies periods of missing data with duration and frequency.
- **Data freshness** — Shows how recently each plant received data.
- **Issue log** — Lists specific data quality issues (negative values, duplicates, outliers).

| Quality Score | Rating | Action |
|---------------|--------|--------|
| ≥ 0.9 | Excellent | No action needed |
| 0.8–0.9 | Good | Monitor |
| 0.6–0.8 | Fair | Investigate gaps |
| < 0.6 | Poor | Immediate remediation required |

### Data Export

📤 Navigate to **Data Management → Data Export** to download data.

**Export options:**

- Select plants, date range, and data columns.
- Choose output format (CSV).
- Download the file directly from the browser.

---

## Settings

### Theme Switching

Toggle between light and dark mode using the **🌙 Dark Mode** switch in the sidebar. The theme is applied using design tokens that update all UI colours — charts, cards, backgrounds, and text.

### Fiscal Year Start

Set the fiscal year start month using the **Fiscal Year Start** dropdown in the sidebar (default: April). This affects how Year-to-Date calculations and financial period groupings are computed.

### User Preferences

Navigate to **Settings** (⚙️ Preferences) to configure:

- Display preferences
- Default date ranges
- Notification settings
- Chart style options

### API Key Management

Administrators can manage API keys via **Admin → API Management** (🔌):

- View configured API endpoints and adapters.
- Test adapter connectivity.
- Update API credentials.

The platform supports the following data source adapters:

| Adapter | Source | Protocol |
|---------|--------|----------|
| EMIG / Juggle | EMIG monitoring platform | REST API |
| SolarGIS | Satellite-derived irradiance | REST API |
| SMA | SMA Sunny Portal / ennexOS | OAuth2 REST API |
| Enphase | Enphase Enlighten | REST API |
| SolarEdge | SolarEdge monitoring | REST API |
| Huawei | Huawei FusionSolar | REST API |
| Fronius | Fronius Solar.web | REST API |
| Generic CSV | Manual file uploads | File upload |

---

## Troubleshooting

### Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "Could not load portfolio data" | Database connection failure | Check that the DuckDB file exists and is not locked by another process. Restart the application. |
| "You do not have permission" | Insufficient role for the requested page | Contact your administrator to request role upgrade. |
| "Account locked" | 5 failed login attempts within 15 minutes | Wait 15 minutes and try again. Contact admin if you've forgotten your password. |
| "No plants registered" | Empty plant registry | Navigate to Plant Management and register your first plant. |
| Blank charts or "No data" | No data in the selected date range | Adjust the date range. Verify data was imported for the plant. |

### Data Not Loading

If data appears stale or fails to load:

1. **Check data freshness** — Go to Data Quality Dashboard and review the "Last Data" column.
2. **Trigger a manual data pull** — Go to Plant Management, select the plant, and click **Fetch Data**.
3. **Verify API connectivity** — Go to API Management and test the adapter health.
4. **Check the server logs** — Look for connection errors or API rate-limiting in the application logs.
5. **Restart the application** — Some caching issues are resolved by restarting Streamlit.

### Report Generation Issues

If reports fail to generate:

1. **Ensure sufficient data** — Monthly reports require at least one month of data for all selected plants.
2. **Check disk space** — Reports are saved to the `reports/` directory on the server.
3. **Review error messages** — The Report Builder will display specific errors if template rendering fails.
4. **Clear the report cache** — Delete files in `reports/tmp/` and retry.

### Performance Issues

If the application is running slowly:

1. **Reduce the date range** — Large date ranges query more data.
2. **Use cached views** — Ask your administrator to enable materialised views for frequently accessed data.
3. **Check Redis** — If Redis is configured, ensure it is running and healthy.
4. **Limit concurrent users** — Streamlit runs single-threaded per session; high user counts may degrade performance.

### Getting Help

- Contact your system administrator for account issues, data problems, or feature requests.
- Check the **System Health** page (Admin only) for real-time diagnostics.
- Review the `ADMIN_GUIDE.md` for server-side troubleshooting.

---

*© AMPYR Energy — Solar Portfolio Manager v1.1.0*
