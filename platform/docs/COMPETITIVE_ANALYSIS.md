# Solar Monitoring & Analysis Platform — Competitive Analysis

*Compiled: July 2025*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Platform Profiles](#platform-profiles)
3. [Feature Comparison Matrix](#feature-comparison-matrix)
4. [Industry Standard KPIs](#industry-standard-kpis)
5. [IEC 61724 Standard](#iec-61724-standard)
6. [UI/UX Design Patterns](#uiux-design-patterns)
7. [Data Architecture & Gap Handling](#data-architecture--gap-handling)
8. [CMMS Integration Patterns](#cmms-integration-patterns)
9. [Best Practices — World-Class Solar Monitoring UI](#best-practices--world-class-solar-monitoring-ui)
10. [Opportunities & Differentiation](#opportunities--differentiation)

---

## Executive Summary

The solar monitoring and asset performance management market is dominated by a handful of full-stack platforms (Power Factors Unity, AlsoEnergy PowerTrack, GreenPowerMonitor Horizon) and complemented by inverter-native monitoring (SMA, Enphase, SolarEdge), specialized analytics firms (Solargis, Quintas Energy), and operations management platforms (Bazefield). The market is converging toward:

- **Multi-technology portfolios** (solar + wind + storage + hybrid) on a single platform
- **Edge-to-cloud architectures** with SCADA/DAS at the plant level feeding cloud analytics
- **AI/ML-driven predictive maintenance** and anomaly detection
- **Integrated CMMS / Field Service Management** (tickets → work orders → completion)
- **Loss waterfall disaggregation** as a core analysis paradigm
- **OEM-agnostic data normalization** across heterogeneous fleets
- **Tiered product offerings** (Core → Pro → Elite) to capture different market segments

The top platforms manage 25–100+ GW across 50–90+ countries, serving asset owners, O&M providers, EPCs, and investors.

---

## Platform Profiles

### 1. GreenPowerMonitor (GPM) — DNV

**Product:** GPM Horizon (cloud) + GPM SCADA/EMS/PPC/HEMS (on-site)

**Scale:** 7,500+ facilities, 90+ countries, 100+ GW managed

**Architecture:**
- **On-site:** GPM SCADA (utility-scale controller), GPM PPC (power plant controller — real-time + reactive power), GPM EMS (BESS grid compliance), GPM HEMS (hybrid PV+BESS control)
- **Cloud:** GPM Horizon (multi-tech asset management), GPM Plus (portfolio reporting/forecasting), GPM Portal (customizable web portal), Energy Data Tagger (data standardization)
- **Analytics:** SolarGEMINI / WindGEMINI (DNV advanced analytics), Gemini predictive module

**Tiered Offering:**
| Tier | Modules |
|------|---------|
| **Core** | Overview, Monitor, Alarms, Data Studio |
| **Pro** | + Analysis, Budgets, Reports, Revenues, Tickets |
| **Elite** | + Logbook, KPIs, Forecast, Planning, Gemini (Predictive), Mobile App |

**Key Features:**
- Multi-technology: wind, solar, storage on one platform
- Holistic portfolio view: sensor-level to portfolio-level aggregation
- Predictive diagnostics via Gemini (anomaly detection, failure prevention)
- Modular subscription — pick only the modules you need
- ISO/IEC 27001 cybersecurity certification (DNV parent)
- Data standardization tools (Energy Data Tagger)
- Financial impact tracking (revenue/budgets modules)
- Mobile app (Elite tier only)

**Differentiators:** DNV brand credibility, integrated SCADA-to-cloud stack, SolarGEMINI/WindGEMINI analytics, modular tiered pricing, massive global footprint.

---

### 2. Power Factors — Unity REMS

**Product:** Unity Renewable Energy Management Suite

**Scale:** 600+ customers, ranked #1 EMS & M&C provider (Guidehouse)

**Architecture:**
- **Local:** SCADA-EMS, Power Plant Controller
- **Central:** Central SCADA-EMS
- **Cloud:** Asset Performance Management (APM), Field Service Management (FSM), Asset Oversight, Invoice Management, Advanced Insights (AI)

**Key APM Features:**
- High-frequency SCADA/inverter/BESS data ingestion with low latency
- Event-driven architecture — automatic downstream calculations on new/backfilled data
- Scalable event processing — auto-categorize downtime, curtailment, underperformance
- Root-cause diagnostics — loss disaggregation via interactive loss waterfalls
- Configurable performance models — OEM-specific assumptions, resource-adjusted baselines
- Condition-based maintenance via thermal performance data analysis
- Standards-ready reporting — automated, continuously updated loss + compliance reports
- Fleet-to-component drill-downs with real-time KPIs
- Multi-asset benchmarking (solar, wind, storage)
- Heat maps, scatter plots, automated insights
- OEM-agnostic — normalize data across vendors

**Field Service Management (CMMS):**
- Integrated work order management
- Planning & scheduling optimization
- Inventory & purchasing
- Contractual compliance tracking
- Asset registry
- Cost tracking
- Dashboards & reporting
- APM events automatically create work orders (closed-loop)

**Ecosystem Integration:**
- SCADA & controls integration (any system)
- OEM-agnostic compatibility
- Market interfaces (dispatch, bidding, compliance)
- Commercial Asset Management (CAM) — link asset health to financial outcomes
- CMMS integration (any work management system, or native Unity FSM)

**Differentiators:** Most comprehensive end-to-end suite (SCADA → APM → FSM → CAM), event-driven real-time architecture, loss waterfall disaggregation, AI-powered Advanced Insights, closed-loop APM→FSM workflow, #1 ranking by Guidehouse.

---

### 3. AlsoEnergy / Stem — PowerTrack

**Product:** PowerTrack (edge-to-cloud monitoring platform)

**Scale:** 200,000+ sites, 25+ GW, 50+ countries, ranked #1 solar & storage monitoring vendor

**Key Features:**
- Edge-to-cloud architecture (hardware + software)
- Diagnostics & event management
- Remote troubleshooting
- Customized reporting
- Descriptive & performance analytics
- Supervisory dashboards
- System of record
- BESS management
- PPC configuration & remote control
- Non-native data ingest (third-party data sources)
- Overlays & portfolio aggregation
- Agency/financial reporting
- CMMS integration
- APIs for workflow integration

**Target Users:** Asset owners, EPCs, field service teams, control centers, performance engineers

**Differentiators:** Largest installed base (200K+ sites), edge hardware included, strong in residential+C&I+utility, Stem battery intelligence integration, established data ingest from non-native sources.

---

### 4. Solargis

**Product:** Suite of SaaS tools for solar resource assessment, monitoring, and forecasting

**Scale:** 1,200+ organizations, 9,000+ projects, 24 years, 99% global coverage

**Products:**
| Product | Purpose |
|---------|---------|
| **Prospect** | Site selection & screening |
| **Evaluate** | 15-min TMY data, 30-yr history, 3D designer, ray tracing |
| **Monitor** | Gap-free solar data, near real-time PV performance assessment |
| **Forecast** | 14-day power output forecasts, 15-min nowcasting |
| **Analyst** | Visualize large datasets, error cleaning, multi-source harmonization |
| **Integration** | APIs (LTA, TMY, Monitor, Forecast, Historical TS), FTP |
| **Solarmaps** | Interactive solar resource maps |

**Key Features:**
- 250m spatial resolution, down to 1-min temporal resolution
- Gap-free irradiance data via proprietary satellite-derived algorithms
- Multi-source data harmonization
- Site-specific bankable solar data
- Error cleaning & quality control tooling
- API-first for integration

**Differentiators:** Gold standard for solar resource data, gap-free satellite-derived irradiance, bankable data accepted by investors, global coverage, strong in project development phases. Less of a real-time O&M monitoring platform and more of a data/analytics provider.

---

### 5. Bazefield (Univers)

**Product:** Renewable assets operations management system

**Architecture:** Windows-based with web/mobile access, strong data historian backbone

**Monitoring Features:**
- Real-time portfolio, plant, and asset-level monitoring
- Customizable workspaces and dashboards ("control room" function)
- Alarms & event management
- Production values, availability measures, capacity factor KPIs
- Substation mimics, met masts, forecast integration

**Analysis Features:**
- Power curve analytics (compare before/after OEM upgrades)
- Alarm statistics (frequency + duration + root cause filtering)
- Trending tool (time series — measured or calculated values)
- Availability analytics (contractual categorization or IEC-61400)
- 2D/3D plotter (historical data down to tag level with filter conditions)

**Operations Management:**
- Weather forecasting integration
- HSE & site activity tracking (work orders, contacts, safe passes, inductions)
- Availability planner (schedule corrective + planned maintenance)
- CMMS integration capability

**Technical Architecture:**
- OPC standard for data collection
- IEC 60870-5-101/104, FTP/files, ODBC/SQL, OSIsoft PI historian support
- IEC 61400-25 data model standard
- RESTful APIs + .NET SDK
- Turn-key support for major wind OEMs (Vestas, Siemens, Nordex, GE, etc.)
- iPad, iPhone, Android, Windows device support

**Differentiators:** Strong data historian backbone, IEC standards compliance, deep wind expertise (expanding to solar), HSE/site activity tracking, power curve analysis.

---

### 6. SMA — Sunny Portal / ennexOS

**Product:** Sunny Portal (legacy) → ennexOS (next-gen platform)

**Key Features:**
- 5-minute data resolution
- Remote parameter configuration
- Detailed AC/DC inverter data
- Real-time data without delay
- ISO/IEC 27001 certified
- Data Manager L for power plants
- Power Plant Manager for turnkey energy management
- Developer Portal for API access

**Target:** Primarily SMA inverter ecosystem (installer + asset owner)

**Differentiators:** Deep inverter-level detail for SMA equipment, transitioning to modern ennexOS platform, established install base. Limited to SMA ecosystem.

---

### 7. Enphase — Enphase App / Enlighten

**Product:** Enphase App (consumer + installer), Enlighten (installer portal)

**Key Features:**
- Panel-level production monitoring
- Grid import/export tracking
- Appliance management
- System health review
- Reports by day/week/month/year
- "Clean and easy-to-read graphs and infographics"
- Mobile-first (iOS/Android)

**Target:** Primarily residential and small commercial

**Differentiators:** Best-in-class residential UX, panel-level granularity via microinverters, consumer-friendly design. Not designed for utility-scale.

---

### 8. SolarEdge — Monitoring Platform

**Product:** SolarEdge Monitoring (residential), ONE for C&I (commercial)

**Key Features:**
- Fleet management dashboard
- Module-level and inverter-level performance data
- Automated alerts down to module level
- Map-based fleet navigation
- Mobile fleet management (SolarEdge GO app)
- Edge Academy training platform

**Target:** Residential + C&I installers and asset owners

**Differentiators:** Module-level optimization/monitoring via power optimizers, map-based fleet view, strong installer tools. Ecosystem-locked to SolarEdge hardware.

---

### 9. Reuniwatt

**Product:** Solar radiation and cloud forecasting solutions

**Key Products:**
- **SunSat™** — Satellite-based irradiance processing
- **Sky InSight™** — All-sky camera imagers for local cloud sensing
- **InstaCast™** — Intra-hour solar nowcasting

**Focus:** Forecasting specialist rather than full monitoring platform. Useful as a data input to other monitoring systems. Strong in ramp-rate forecasting and grid integration.

---

### 10. Quintas Energy — Analytics

**Product:** Data consulting, BI platform (Ariadne portal), analytics models

**Scale:** 12 countries

**Analytics Models:**
| Model | Purpose |
|-------|---------|
| Project Development Control | Development phase analytics |
| Technical Performance Automation | Automated technical KPIs |
| Revenue Process Automation | Revenue tracking & optimization |
| Expenditure Validation System | Cost validation |
| Maintenance Lifecycle Management | Maintenance optimization |
| Contract Performance Automation | Contract compliance analytics |
| String Performance Diagnostics | String-level fault detection |
| Tracker Performance Diagnostics | Tracker health analysis |
| Grid Impact Analytics | Grid-related loss analysis |

**Methodology:** Understanding → Integration → Construction → Implementation → Operation (5-step)

**Differentiators:** Consulting-led analytics, string-level and tracker-level diagnostics, grid impact analysis. More of a services/analytics firm than a SaaS platform.

---

### 11. Meteocontrol

**Product:** VCOM Cloud monitoring platform + hardware (data loggers, sensors)

**Key Features:**
- Independent data logger connecting to multiple inverter brands
- VCOM Cloud monitoring portal
- Performance ratio calculation
- Yield monitoring
- Alarm management
- Report generation

**Differentiators:** Hardware-agnostic data logging, strong in European PV market. Mid-tier platform.

---

### 12. Powerhub

**Status:** Website not accessible during research. Known as a renewable energy portfolio management platform focused on financial reporting and asset management workflows.

---

### 13. Fronius — Solar.web

**Product:** Solar.web monitoring portal

**Key Features:**
- Inverter and system monitoring
- Energy flow visualization
- Archive data access
- System comparison tools

**Target:** Fronius inverter ecosystem, residential/C&I

---

### 14. Additional Notable Players

| Platform | Focus |
|----------|-------|
| **Omnidian** | Residential solar performance insurance + monitoring |
| **Solytic** | Generic device-agnostic cloud solar monitoring |
| **Solar Analytics** | Smart logger + analytics (Australia-focused) |
| **Sungrow iSolarCloud** | Sungrow inverter ecosystem monitoring |
| **Huawei FusionSolar** | Huawei inverter ecosystem, AI-driven optimization |

---

## Feature Comparison Matrix

### Core Monitoring & Analytics

| Feature | GPM Horizon | Power Factors Unity | AlsoEnergy PowerTrack | Solargis | Bazefield | SMA ennexOS | Enphase | SolarEdge |
|---------|:-----------:|:-------------------:|:---------------------:|:--------:|:---------:|:-----------:|:-------:|:---------:|
| Real-time monitoring | ✅ | ✅ | ✅ | ⚠️ NRT | ✅ | ✅ | ✅ | ✅ |
| Portfolio-level view | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Limited | ❌ | ✅ Fleet |
| Plant-level dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Inverter-level data | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| String/module-level | ⚠️ | ✅ | ✅ | ❌ | ⚠️ | ❌ | ✅ Panel | ✅ Module |
| Performance ratio (PR) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| Availability tracking | ✅ | ✅ | ✅ | ❌ | ✅ IEC | ⚠️ | ❌ | ❌ |
| Specific yield | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ |
| Loss waterfall | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Curtailment analysis | ✅ | ✅ | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| Clipping analysis | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Soiling/fouling analysis | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Thermal loss analysis | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Shading analysis | ⚠️ | ⚠️ | ⚠️ | ✅ 3D | ❌ | ❌ | ❌ | ❌ |
| Trend analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| Heat maps | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Scatter plots | ⚠️ | ✅ | ⚠️ | ✅ | ✅ 2D/3D | ❌ | ❌ | ❌ |

### Alerts, Events & Ticketing

| Feature | GPM Horizon | Power Factors | AlsoEnergy | Bazefield | SMA | Enphase | SolarEdge |
|---------|:-----------:|:-------------:|:----------:|:---------:|:---:|:-------:|:---------:|
| Alarm management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Event categorization | ✅ | ✅ Auto | ✅ | ✅ | ⚠️ | ❌ | ⚠️ |
| Ticketing system | ✅ Pro+ | ✅ Native | ⚠️ | ✅ HSE | ❌ | ❌ | ❌ |
| Work order mgmt (CMMS) | ⚠️ | ✅ FSM | ✅ Integration | ✅ | ❌ | ❌ | ❌ |
| Automated event→ticket | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |
| Root cause analysis | ✅ Gemini | ✅ Advanced | ✅ | ✅ | ❌ | ❌ | ❌ |
| Predictive maintenance | ✅ Gemini | ✅ AI | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |

### Reporting & Financial

| Feature | GPM Horizon | Power Factors | AlsoEnergy | Solargis | Bazefield | SMA |
|---------|:-----------:|:-------------:|:----------:|:--------:|:---------:|:---:|
| Automated reports | ✅ Pro+ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| Budget tracking | ✅ Pro+ | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| Revenue tracking | ✅ Pro+ | ✅ CAM | ✅ Agency | ❌ | ❌ | ❌ |
| Invoice management | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Financial impact | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Export to BI tools | ⚠️ | ✅ | ✅ | ✅ API | ⚠️ | ❌ |
| Contractual compliance | ⚠️ | ✅ FSM | ⚠️ | ❌ | ✅ IEC | ❌ |

### Integration & API

| Feature | GPM Horizon | Power Factors | AlsoEnergy | Solargis | Bazefield | SMA |
|---------|:-----------:|:-------------:|:----------:|:--------:|:---------:|:---:|
| REST API | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ Dev Portal |
| SCADA integration | ✅ Native | ✅ Native | ✅ | ❌ | ✅ OPC | ⚠️ |
| OEM-agnostic | ✅ | ✅ | ✅ | N/A | ✅ | ❌ SMA only |
| Non-native data ingest | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| CMMS integration | ⚠️ | ✅ Native + API | ✅ API | ❌ | ✅ | ❌ |
| Market/grid interfaces | ✅ PPC | ✅ | ⚠️ | ❌ | ⚠️ | ⚠️ |
| SDK available | ❌ | ⚠️ | ⚠️ | ✅ | ✅ .NET + REST | ✅ |

### Technology Coverage

| Capability | GPM | Power Factors | AlsoEnergy | Solargis | Bazefield | SMA | Enphase | SolarEdge |
|------------|:---:|:-------------:|:----------:|:--------:|:---------:|:---:|:-------:|:---------:|
| Solar PV | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Wind | ✅ | ✅ | ⚠️ | ❌ | ✅ Primary | ❌ | ❌ | ❌ |
| BESS / Storage | ✅ | ✅ | ✅ | ❌ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Hybrid plants | ✅ HEMS | ✅ | ⚠️ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| Hydro | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |

### Mobile & UX

| Feature | GPM Horizon | Power Factors | AlsoEnergy | Bazefield | SMA | Enphase | SolarEdge |
|---------|:-----------:|:-------------:|:----------:|:---------:|:---:|:-------:|:---------:|
| Mobile app | ✅ Elite | ⚠️ | ⚠️ | ✅ Multi-device | ✅ | ✅ Best-in-class | ✅ GO app |
| Responsive web | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Map-based navigation | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ✅ |
| Custom dashboards | ✅ Data Studio | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Data export (CSV/Excel) | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |

**Legend:** ✅ = Full support | ⚠️ = Partial/limited | ❌ = Not available

---

## Industry Standard KPIs

### Primary Performance Metrics (per IEC 61724)

| KPI | Definition | Formula | Industry Benchmark |
|-----|------------|---------|-------------------|
| **Performance Ratio (PR)** | Ratio of actual AC output to theoretical DC output under reference conditions. Measures total system losses. | PR = (E_AC / P_STC) / (H_POA / G_STC) | >80% for modern utility-scale |
| **Reference Yield (Y_r)** | Total in-plane irradiance divided by reference irradiance (1000 W/m²) | Y_r = H_POA / G_STC [kWh/kW] | Location-dependent |
| **Final Yield (Y_f)** | Net AC energy output divided by nameplate DC capacity | Y_f = E_AC / P_STC [kWh/kW] | Varies by location/technology |
| **Specific Yield** | Annual energy production per kW of installed capacity | kWh/kWp/year | 1,200–2,200 depending on location |
| **Capacity Utilization Factor (CUF)** | Ratio of actual energy output vs max possible at nameplate capacity over a period | CUF = E_actual / (P_rated × Hours) | 15–25% typical for solar |
| **Availability** | Time the system is available to produce energy | A = (Total hours - Downtime) / Total hours | >98% target |

### Energy Loss Categories (Standard Waterfall)

| Loss Category | Description | Typical Range |
|---------------|-------------|---------------|
| **Grid curtailment** | Energy lost due to grid operator instructions | 0–10%+ |
| **Export limit losses** | Energy lost due to contracted export capacity limits | 0–5% |
| **Inverter clipping** | DC power exceeds inverter AC rating | 0–3% |
| **Soiling/Fouling** | Dust, bird droppings, pollen on panels | 1–5% |
| **Shading** | Near/far shading from structures, vegetation, inter-row | 0–5% |
| **Thermal losses** | Cell temperature above STC (25°C) reduces efficiency | 2–10% |
| **Wiring/cable losses** | DC and AC cable resistance losses | 1–3% |
| **Inverter efficiency** | Conversion efficiency below nameplate | 2–4% |
| **Transformer losses** | Step-up transformer losses | 0.5–2% |
| **Degradation** | Panel aging/degradation | 0.5–1%/year |
| **Snow/ice** | Coverage preventing generation | Seasonal |
| **Downtime** | Equipment failure, maintenance | 1–3% |
| **Mismatch** | Module-to-module parameter variation | 0.5–2% |

### Availability Categories (Common Industry Practice)

| Category | Description |
|----------|-------------|
| **Contractual Availability** | Per O&M contract terms (excludes force majeure, grid outages) |
| **Technical Availability** | Equipment uptime regardless of external factors |
| **Energy-based Availability** | Weighted by irradiance (accounts for when downtime occurs) |
| **Time-based Availability** | Simple percentage of hours online |
| **IEC 61400-based** | Standard categorization system (commonly used in wind, adopted in solar) |

---

## IEC 61724 Standard

### Overview

**IEC 61724-1:2017** — *Photovoltaic system performance — Part 1: Monitoring*

The international standard for PV system performance monitoring, defining:

### Monitoring Classes

| Class | Label | Irradiance Sensor | Use Case |
|-------|-------|-------------------|----------|
| **A** | High accuracy | Thermopile pyranometer (secondary standard, ≤3% uncertainty) or PV reference device (≤3%) | Utility-scale, bankable reporting |
| **B** | Medium accuracy | First class pyranometer (≤8%) or PV reference device (≤8%) or satellite-derived | Commercial, portfolio monitoring |
| **C** | Basic accuracy | Any sensor type, or satellite-derived | Residential, basic monitoring |

### Standard Requirements

- **Data acquisition**: Defines minimum sensor requirements, measurement intervals, data quality checks
- **Performance metrics**: Standardizes calculation of Performance Ratio, yields, capacity factor
- **Reporting**: Defines standard reporting periods and formats
- **Sensor placement**: POA (plane of array) or GHI (global horizontal irradiance)
- **Temperature**: Ambient and module temperature measurement requirements
- **Maintenance**: Re-calibration schedules per accuracy class

### Related Standards

| Standard | Scope |
|----------|-------|
| IEC 61724-1 | Monitoring (sensors, data acquisition, metrics) |
| IEC 61724-2 | Capacity evaluation |
| IEC 61724-3 | Energy evaluation method |
| IEC 61853 | Module performance testing and energy rating |
| IEC 61215 | Module design qualification |
| IEC 61730 | Module safety qualification |
| IEC 62446 | Grid-connected PV systems — commissioning + documentation |
| IEC 61400-25 | Data model standard for wind (adopted by Bazefield for solar) |

---

## UI/UX Design Patterns

### Common Navigation Patterns Across Platforms

1. **Portfolio → Plant → Device Drill-Down** (Universal pattern)
   - Portfolio map/list → select plant → plant dashboard → inverter/string detail
   - Used by: GPM, Power Factors, AlsoEnergy, SolarEdge, Bazefield

2. **Dashboard-First Architecture**
   - Landing page = portfolio KPI summary
   - One-click to anomaly/issue lists
   - Color-coded status indicators (green/yellow/red)

3. **Sidebar Navigation**
   - Module-based sidebar (monitoring, analysis, reporting, settings)
   - Used by: GPM, Power Factors, AlsoEnergy

4. **Tab-Based Module Switching**
   - Within a plant view, tabs for: Overview | Live Data | Events/Alarms | Analysis | Reports
   - Used by: Most platforms

5. **Map-Based Fleet View**
   - Geographic map with plant markers (color = health status)
   - Click marker → plant detail
   - Used by: SolarEdge, Power Factors, GPM

### Data Visualization Patterns

| Pattern | Usage | Platforms |
|---------|-------|-----------|
| **Loss Waterfall Chart** | Disaggregate energy losses from theoretical to actual | Power Factors, AlsoEnergy |
| **Time-Series Line Charts** | Production, irradiance, temperature over time | All platforms |
| **Heat Maps** | Inverter/string performance grid, time-of-day patterns | Power Factors, AlsoEnergy |
| **Scatter Plots** | PR vs irradiance, power vs temperature correlations | Power Factors, Bazefield, Solargis |
| **Bar Charts** | Monthly/quarterly comparisons, budget vs actual | All platforms |
| **Gauge/Donut Charts** | KPI targets (PR, availability) | GPM, SMA |
| **Sankey Diagrams** | Energy flow visualization | Enphase (simplified) |
| **Sparklines** | Inline trend indicators in tables | Power Factors |
| **Traffic Light Indicators** | Quick health status | All platforms |
| **2D/3D Plots** | Advanced analysis with filter conditions | Bazefield |

### Alert/Notification Patterns

- **Priority-based**: Critical / Warning / Info tiers
- **Channel routing**: Email, SMS, in-app, push notification
- **Aggregation**: Batch similar alerts to prevent notification fatigue
- **Contextual**: Alert includes plant, device, metric, value, threshold, and suggested action
- **Escalation**: Auto-escalate if unacknowledged within SLA period

---

## Data Architecture & Gap Handling

### Data Flow Architecture (Industry Standard)

```
[Sensors/Meters] → [Data Logger/Gateway] → [SCADA/DAS] → [Cloud Platform]
                                                              ↓
                                              [Data Lake / Time-Series DB]
                                                              ↓
                                              [ETL / Calculations Engine]
                                                              ↓
                                              [Analytics / Dashboards / Reports]
```

### Data Resolution Standards

| Level | Resolution | Use Case |
|-------|-----------|----------|
| Real-time | 1–5 second | SCADA control, power plant controller |
| High-frequency | 1–5 minute | Performance monitoring, event detection |
| Standard monitoring | 5–15 minute | Portfolio monitoring, KPI calculation |
| Reporting | Hourly/daily/monthly | Reports, budgets, contractual compliance |

### Data Gap Handling Best Practices

| Approach | Description | Used By |
|----------|-------------|---------|
| **Satellite irradiance fill** | Replace missing sensor data with satellite-derived irradiance | Solargis (gap-free product), Power Factors |
| **Linear interpolation** | Fill short gaps (<1 hour) with interpolated values | Most platforms |
| **Flagged exclusion** | Mark gaps and exclude from KPI calculations with flag | IEC 61724 recommended |
| **Store-and-forward** | Buffer data locally during connectivity loss, upload when restored | Power Factors (event-driven), AlsoEnergy (edge) |
| **Backfill processing** | Automatically reprocess calculations when backfilled data arrives | Power Factors (event-driven architecture) |
| **Multi-source harmonization** | Blend multiple data sources with quality-weighted averaging | Solargis Analyst |
| **Quality scoring** | Assign data quality scores (0–100%) to each data point | Solargis, Power Factors |
| **Expected value substitution** | Replace missing data with modeled expected values (clearly flagged) | Various |

### Data Quality Indicators (Common Practice)

- **Completeness**: % of expected data points received
- **Accuracy**: Deviation from reference measurements
- **Timeliness**: Latency from measurement to availability
- **Consistency**: Cross-validation between related sensors
- **Plausibility**: Range checks, rate-of-change checks, physical consistency

---

## CMMS Integration Patterns

### Industry Approaches

#### 1. Native CMMS (Built-in)
**Example:** Power Factors Unity FSM, GPM Horizon (Tickets module)

- Work orders created automatically from performance events
- Inventory and parts management
- Planned maintenance scheduling
- Cost tracking and contractual compliance
- Closed-loop: Event → Ticket → Work Order → Completion → Updated Availability

#### 2. Third-Party CMMS Integration via API
**Example:** AlsoEnergy, Bazefield

- API/webhook integration with SAP PM, Maximo, Fiix, eMaint, etc.
- Bi-directional sync: platform events → CMMS work orders, completion → platform
- Often requires custom middleware or integration platform

#### 3. Hybrid Approach
**Example:** Power Factors (native FSM + third-party CMMS API)

- Use native CMMS for core workflows
- Integrate with enterprise ERP/EAM for financial consolidation
- Flexible depending on customer's existing tooling

### Standard CMMS Workflow in Solar

```
1. Performance Deviation Detected (automated)
   ↓
2. Event Created & Categorized (downtime, underperformance, alarm)
   ↓
3. Ticket Created (auto or manual)
   ↓
4. Work Order Generated (with asset registry, location, history)
   ↓
5. Technician Dispatched (scheduling, route optimization)
   ↓
6. Work Performed (mobile app, photo documentation, parts used)
   ↓
7. Completion Logged (time, cost, resolution, root cause)
   ↓
8. Availability Updated (automatic recalculation)
   ↓
9. Reporting (maintenance KPIs, MTTR, cost per MW, etc.)
```

### Key CMMS KPIs for Solar

| KPI | Definition |
|-----|------------|
| **MTTR** | Mean Time to Repair |
| **MTBF** | Mean Time Between Failures |
| **Cost per MWh** | O&M cost normalized to production |
| **Cost per MW** | O&M cost normalized to capacity |
| **Work Order Closure Rate** | % of work orders closed within SLA |
| **Planned vs Reactive Ratio** | Ratio of planned maintenance to reactive/corrective |
| **Parts Inventory Turnover** | How efficiently spare parts are consumed |

---

## Best Practices — World-Class Solar Monitoring UI

### 1. Progressive Disclosure (Portfolio → Plant → Device)
- Start with portfolio-level health summary
- Enable one-click drill-down to plant, then device level
- Never overwhelm with detail at the top level
- Breadcrumb navigation for easy back-tracking

### 2. Time is the Primary Axis
- Every major view should be filterable by time range
- Quick presets: Today, Yesterday, This Week, This Month, This Year, Custom
- Comparison periods: This month vs same month last year
- Time-series charts should be the default visualization

### 3. Exception-Based Monitoring
- Default view highlights only anomalies and issues
- "Everything is fine" should be the quietest state
- Sort by impact (revenue lost, energy lost) not just count
- Automated prioritization of issues

### 4. Contextual KPIs
- Always show KPIs in context: actual vs expected vs budget
- Traffic light indicators for quick scanning
- Trend arrows (↑↓→) for directionality
- Don't show raw numbers without interpretation aids

### 5. Loss Attribution
- Every kWh of lost energy should be attributable to a cause
- Loss waterfall charts are the gold standard
- Enable drill-down from total loss → category → event → device
- Support both energy-based and financial-based loss views

### 6. Actionable Alerts
- Every alert should suggest a next action
- Link directly to the affected device/event
- Include relevant context (history, severity, estimated impact)
- Avoid alert fatigue through intelligent aggregation and suppression

### 7. Self-Service Reporting
- Configurable report templates
- Scheduled automated delivery
- Export formats: PDF, Excel, CSV, API
- Standard reports: Monthly owner report, O&M report, investor report
- Custom report builder with drag-and-drop

### 8. Mobile-First for Field Teams
- Native mobile app or responsive web
- Key functions: view alerts, acknowledge events, log work, take photos
- Offline capability for remote sites
- GPS/map integration for navigation

### 9. Data Confidence Indicators
- Show data quality/completeness metrics
- Flag estimated vs measured values
- Transparency about data gaps and how they're handled
- Confidence intervals on calculated metrics

### 10. Comparison & Benchmarking
- Compare plants within portfolio
- Compare periods (MoM, YoY)
- Compare actual vs budget/PVsyst model
- Normalize for weather to enable fair comparisons

---

## Opportunities & Differentiation

### Gaps in the Market (Based on Research)

| Gap | Description | Opportunity |
|-----|-------------|-------------|
| **Export limit loss tracking** | Few platforms specifically track and visualize export limit losses as a distinct loss category | Build dedicated export limit loss analysis (you already have this module) |
| **Australian market specifics** | Most platforms are US/EU-focused, limited Australian grid/regulatory support | Deep Australian NEM integration, AEMO compliance |
| **Mid-market pricing** | Top platforms (GPM, PF) target 100MW+ portfolios; Enphase/SolarEdge are residential | Target 1–50MW C&I and small utility-scale |
| **Accessibility of advanced analytics** | Loss waterfall, clipping, thermal analysis are premium features | Make these available in base tier |
| **PVsyst model import & comparison** | Most platforms have basic budget comparison but weak PVsyst model integration | Direct PVsyst import, automatic expected vs actual |
| **Integrated monthly reporting** | Monthly owner/investor reports often require manual Excel work | Automated monthly report generation (you have this module) |
| **Database transparency** | Most platforms are black boxes — users can't query raw data | Database viewer / data explorer for power users |
| **Single-tenancy simplicity** | Enterprise platforms have complex multi-tenant setup | Simple single-portfolio deployment |

### Your App's Existing Strengths (vs. Competitors)

Based on your codebase, you already have modules that many competitors either lack or gate behind premium tiers:

1. **Clipping Analysis** — Dedicated module (competitors often bundle or omit)
2. **Curtailment Analysis** — Separate focused module
3. **Export Limit Loss Tracking** — Rare in competitive landscape
4. **Loss Waterfall** — Premium feature at competitors, you have it built-in
5. **Fouling/Soiling Analysis** — Dedicated module
6. **Shading Analysis** — Dedicated module
7. **Thermal Loss Analysis** — Dedicated module
8. **Monthly Reporting with Branding** — Integrated reporting bridge
9. **Database Viewer** — Raw data access (unique transparency)
10. **Data Explorer** — Self-service data investigation
11. **POA Import** — Direct irradiance data management
12. **System Health Monitoring** — Application-level observability

### Recommended Focus Areas

1. **Polish the loss waterfall** — This is the signature visualization of top-tier platforms. Make yours best-in-class with drill-down capability, financial impact overlay, and comparison periods.

2. **Strengthen the alert→ticket→resolution pipeline** — Power Factors' closed-loop APM→FSM workflow is the industry benchmark. Even a lightweight version adds significant value.

3. **Add Performance Ratio trending with weather normalization** — Show PR adjusted for actual irradiance/temperature vs STC conditions.

4. **Implement data quality scoring** — Show data completeness and quality indicators. This builds trust with asset owners and investors.

5. **Build automated monthly report generation** — You have the monthly reporting module. Make it one-click: select month, generate branded PDF with standard KPIs, loss breakdown, and commentary fields.

6. **Map-based portfolio view** — SolarEdge and Power Factors both use this effectively. Even a simple Leaflet/Mapbox view with plant markers adds professionalism.

7. **Comparison/benchmarking views** — Compare plants side-by-side, normalized for weather. This is a key ask from portfolio managers.

8. **Mobile responsiveness** — Ensure Streamlit app works well on tablets for field use.

---

*End of Competitive Analysis*
