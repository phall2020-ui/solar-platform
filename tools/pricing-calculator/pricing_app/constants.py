"""
AMPYR Distributed Energy - Pricing Calculator Constants & Lookup Tables
========================================================================
All lookup tables, default assumptions, and brand constants used across
the pricing calculator application.
"""

# ── Brand Colours (extracted from AMPYR logo) ─────────────────────────
BRAND_NAVY = "#0B1A2E"
BRAND_NAVY_LIGHT = "#122240"
BRAND_NAVY_MID = "#1A3050"
BRAND_TEAL = "#00B4A0"
BRAND_TEAL_DARK = "#009985"
BRAND_TEAL_LIGHT = "#33C4B3"
BRAND_WHITE = "#FFFFFF"
BRAND_GREY_LIGHT = "#E8ECF0"
BRAND_GREY = "#8899AA"
BRAND_GREY_DARK = "#4A5568"
BRAND_RED_WARNING = "#E53E3E"
BRAND_AMBER_WARNING = "#ED8936"
BRAND_GREEN = "#38A169"

# ── Credit Score → Target IRR Lookup ──────────────────────────────────
# (lower_bound, upper_bound): target_irr
CREDIT_SCORE_IRR_TABLE = [
    (87, 100, 0.0900),
    (75, 86, 0.0925),
    (71, 74, 0.0950),
    (66, 70, 0.1025),
    (61, 65, 0.1050),
    (51, 60, 0.1075),
    (30, 50, 0.1150),
    (21, 29, 0.1175),
    (0, 20, 0.1250),
]

# ── PPA Price → IRR Uplift Lookup ─────────────────────────────────────
# (lower_bound_pence, upper_bound_pence): uplift
PPA_PRICE_IRR_UPLIFT_TABLE = [
    (0.0, 14.0, 0.0000),
    (14.0, 14.5, 0.0025),
    (14.5, 15.0, 0.0025),
    (15.0, 15.5, 0.0050),
    (15.5, 16.0, 0.0050),
    (16.0, 16.5, 0.0075),
    (16.5, 17.0, 0.0100),
    (17.0, 18.0, 0.0150),
    (18.0, 50.0, 0.0300),
]

# ── O&M Rate per kWp (by project size in MW) ─────────────────────────
# Returns £/kWp/year
def get_om_rate(project_size_kwp: float) -> float:
    mw = project_size_kwp / 1000.0
    if mw < 0.5:
        return 10.0
    elif mw <= 1.0:
        return 8.0
    else:
        return 6.0

# ── Insurance Rate ────────────────────────────────────────────────────
INSURANCE_PER_KWP = 2.5  # £/kWp/year

# ── Transaction Cost Simplified ───────────────────────────────────────
def get_simplified_transaction_cost(project_size_kwp: float) -> float:
    if project_size_kwp < 1300:
        return 15000.0
    else:
        return 25000.0

# ── Transaction Cost Detailed ─────────────────────────────────────────
def get_detailed_transaction_cost(project_size_kwp: float, is_rtb: bool = True) -> float:
    """Calculate detailed transaction costs based on project size."""
    mw = project_size_kwp / 1000.0
    total = 0.0

    # Legal DD / setup
    if mw < 0.5:
        total += 2500.0
    elif mw <= 1.0:
        total += 5000.0
    else:
        total += 10000.0

    # SPV incorporation
    total += 5000.0

    # SPV acquisition
    total += 10000.0

    # Technical DD report
    if is_rtb:
        total += 2500.0
    else:
        total += 3000.0

    # EPC & O&M procurement (RTB only)
    if is_rtb:
        if mw <= 1.0:
            total += 1900.0
        else:
            total += 4750.0

    # Contract admin (RTB only)
    if is_rtb:
        if mw <= 1.0:
            total += 2400.0
        else:
            total += 6250.0

    # Operational metering
    total += 295.0   # SolarEdge plant setup
    total += 500.0   # API integration

    if not is_rtb:
        if mw < 3.0:
            total += 3000.0   # Simple site metering
        else:
            total += 15000.0  # Complex site metering

    return total

# ── Audit & SPV Management ────────────────────────────────────────────
def get_audit_spv_rate(project_size_kwp: float) -> float:
    """Returns £/kWp/year for audit & SPV management."""
    import math
    return min(10000.0 / project_size_kwp, 50.0 * project_size_kwp ** -0.42)

# ── Default Construction Period ───────────────────────────────────────
def get_default_construction_months(project_size_kwp: float) -> int:
    import math
    return max(2, math.ceil(project_size_kwp / 245.0 / 4.0) + 1)

# ── Default Assumptions ──────────────────────────────────────────────
DEFAULTS = {
    # Project
    "project_name": "New Solar Project",
    "project_size_kwp": 500.0,
    "specific_yield": 950.0,
    "epc_per_kwp": 650.0,
    "credit_score": 80,

    # PPA
    "ppa_length_years": 25,
    "ppa_indexation": "CPI",       # RPI / CPI / Fixed
    "fixed_inflation_rate": 0.025,
    "assumed_inflation_rate": 0.025,
    "take_or_pay_pct": 0.80,
    "take_or_pay_method": "% of Generation",
    "solve_method": "PPA Rate",
    "ppa_price_input": 10.0,       # p/kWh (for Dev Fee mode)
    "dev_fee_per_kwp": 100.0,      # £/kWp (for PPA Rate mode)
    "grid_price_pence": 30.0,      # p/kWh for savings comparison
    "grid_price_escalation": 0.03, # 3% annual grid price escalation

    # Construction
    "insurance_construction_per_kwp": 5.0,
    "stamp_duty_pct": 0.005,       # 0.5%
    "contingency_pct": 0.05,       # 5%
    "acquisition_costs": 0.0,

    # Debt
    "debt_gearing": 0.70,          # 70%
    "debt_interest_rate": 0.06,    # 6.0%
    "debt_tenor_years": 17,
    "debt_commitment_fee": 0.0125, # 1.25%
    "dsra_months": 6,
    "capital_moratorium_months": 6,
    "repayment_method": "Annuity", # Annuity / DSCR Target
    "dscr_target": 1.30,

    # Warehousing
    "warehousing_active": False,
    "warehousing_tenor_months": 6,
    "warehousing_project_fee": 0.03,
    "warehousing_all_in_rate": 0.03,
    "warehousing_exit_irr": 0.17,

    # Equity / SHL
    "equity_ltv": 0.30,
    "shl_coupon": 0.08,            # 8%
    "shl_tenor_years": 10,

    # Tax
    "tax_rate": 0.25,
    "vat_rate": 0.20,
    "vat_rebate_delay_months": 2,
    "capital_allowance_method": "DB",  # DB / Straight Line
    "capital_allowance_rate": 0.06,    # 6%
    "enhanced_ca_flag": False,
    "enhanced_ca_pct": 1.0,
    "annual_investment_allowance": 1000000.0,
    "cir_method": "EBITDA",         # EBITDA / Group Limit
    "cir_ebitda_pct": 0.30,
    "cir_group_limit": 2000000.0,

    # Operating costs
    "land_lease": 0.0,
    "inverter_replacement_per_kwp": 35.0,
    "inverter_funding_start_year": 10,
    "inverter_funding_end_year": 20,
    "business_rates_per_kwp": 0.0,
    "asset_management_per_kwp": 3.0,
    "elec_internet_metering_per_kwp": 1.0,

    # Management company fee
    "management_company_fee_pct": 0.03,  # 3%

    # Liquidated damages
    "ld_performance_change_pct": -0.10,
    "ld_total_amount_paid": 0.0,
    "ld_performance_cap_pct": 0.10,
    "ld_delay_cap_pct": 0.10,
    "peak_seasonality_factor": 1.5,

    # Degradation
    "annual_degradation": 0.005,  # 0.5% per year
}

# ── High PPA Price Warning Threshold ─────────────────────────────────
PPA_HIGH_WARNING_PENCE = 18.0  # p/kWh

# ── Project Life ──────────────────────────────────────────────────────
PROJECT_LIFE_YEARS = 35  # used for residual value / depreciation
