"""
AMPYR Distributed Energy - Pricing Calculator Engine
=====================================================
Full financial model: date logic, capex, opex, revenue, debt, tax,
cash flows, IRR calculation, and solver (goal-seek) routines.
"""

import math
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

import numpy_financial as npf
from scipy.optimize import brentq

from . import constants as C


# ── Date Helpers ──────────────────────────────────────────────────────

def first_of_month(d: date) -> date:
    return d.replace(day=1)


def end_of_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1) - timedelta(days=1)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


# ── Lookup Helpers ────────────────────────────────────────────────────

def lookup_credit_score_irr(score: int) -> float:
    for lo, hi, irr in C.CREDIT_SCORE_IRR_TABLE:
        if lo <= score <= hi:
            return irr
    return 0.1250  # worst case


def lookup_ppa_uplift(ppa_pence: float) -> float:
    for lo, hi, uplift in C.PPA_PRICE_IRR_UPLIFT_TABLE:
        if lo <= ppa_pence < hi:
            return uplift
    if ppa_pence >= 50.0:
        return 0.03
    return 0.0


def compute_target_irr(credit_score: int, ppa_pence: float) -> float:
    base = lookup_credit_score_irr(credit_score)
    uplift = lookup_ppa_uplift(ppa_pence)
    return base + uplift


# ── Input Data Class ─────────────────────────────────────────────────

@dataclass
class ModelInputs:
    # Project
    project_name: str = C.DEFAULTS["project_name"]
    cod_date: date = date(2026, 10, 1)
    construction_months: Optional[int] = None  # None = auto-calculate
    credit_score: int = C.DEFAULTS["credit_score"]
    project_size_kwp: float = C.DEFAULTS["project_size_kwp"]
    specific_yield: float = C.DEFAULTS["specific_yield"]
    epc_per_kwp: float = C.DEFAULTS["epc_per_kwp"]

    # PPA
    ppa_length_years: int = C.DEFAULTS["ppa_length_years"]
    ppa_indexation: str = C.DEFAULTS["ppa_indexation"]
    fixed_inflation_rate: float = C.DEFAULTS["fixed_inflation_rate"]
    assumed_inflation_rate: float = C.DEFAULTS["assumed_inflation_rate"]
    take_or_pay_pct: float = C.DEFAULTS["take_or_pay_pct"]
    take_or_pay_method: str = C.DEFAULTS["take_or_pay_method"]

    # Solve
    solve_method: str = C.DEFAULTS["solve_method"]
    ppa_price_input_pence: float = C.DEFAULTS["ppa_price_input"]
    dev_fee_per_kwp: float = C.DEFAULTS["dev_fee_per_kwp"]

    # Customer comparison
    grid_price_pence: float = C.DEFAULTS["grid_price_pence"]
    grid_price_escalation: float = C.DEFAULTS["grid_price_escalation"]

    # Construction
    insurance_construction_per_kwp: float = C.DEFAULTS["insurance_construction_per_kwp"]
    stamp_duty_pct: float = C.DEFAULTS["stamp_duty_pct"]
    contingency_pct: float = C.DEFAULTS["contingency_pct"]
    acquisition_costs: float = C.DEFAULTS["acquisition_costs"]

    # Debt
    debt_gearing: float = C.DEFAULTS["debt_gearing"]
    debt_interest_rate: float = C.DEFAULTS["debt_interest_rate"]
    debt_tenor_years: int = C.DEFAULTS["debt_tenor_years"]
    repayment_method: str = C.DEFAULTS["repayment_method"]
    dscr_target: float = C.DEFAULTS["dscr_target"]
    dsra_months: int = C.DEFAULTS["dsra_months"]
    capital_moratorium_months: int = C.DEFAULTS["capital_moratorium_months"]
    debt_commitment_fee: float = C.DEFAULTS["debt_commitment_fee"]

    # Warehousing
    warehousing_active: bool = C.DEFAULTS["warehousing_active"]

    # Equity / SHL
    equity_ltv: float = C.DEFAULTS["equity_ltv"]
    shl_coupon: float = C.DEFAULTS["shl_coupon"]
    shl_tenor_years: int = C.DEFAULTS["shl_tenor_years"]

    # Tax
    tax_rate: float = C.DEFAULTS["tax_rate"]
    capital_allowance_method: str = C.DEFAULTS["capital_allowance_method"]
    capital_allowance_rate: float = C.DEFAULTS["capital_allowance_rate"]

    # Opex
    land_lease: float = C.DEFAULTS["land_lease"]
    inverter_replacement_per_kwp: float = C.DEFAULTS["inverter_replacement_per_kwp"]
    business_rates_per_kwp: float = C.DEFAULTS["business_rates_per_kwp"]
    asset_management_per_kwp: float = C.DEFAULTS["asset_management_per_kwp"]
    elec_internet_metering_per_kwp: float = C.DEFAULTS["elec_internet_metering_per_kwp"]

    # Management company fee
    management_company_fee_pct: float = C.DEFAULTS["management_company_fee_pct"]

    # Degradation
    annual_degradation: float = C.DEFAULTS["annual_degradation"]

    # LD
    ld_performance_change_pct: float = C.DEFAULTS["ld_performance_change_pct"]
    ld_total_amount_paid: float = C.DEFAULTS["ld_total_amount_paid"]
    ld_performance_cap_pct: float = C.DEFAULTS["ld_performance_cap_pct"]
    ld_delay_cap_pct: float = C.DEFAULTS["ld_delay_cap_pct"]
    peak_seasonality_factor: float = C.DEFAULTS["peak_seasonality_factor"]

    def effective_construction_months(self) -> int:
        if self.construction_months is not None:
            return self.construction_months
        return C.get_default_construction_months(self.project_size_kwp)


# ── Model Results ────────────────────────────────────────────────────

@dataclass
class YearCashflow:
    year: int
    year_label: str
    generation_kwh: float = 0.0
    ppa_price_pence: float = 0.0
    revenue: float = 0.0
    grid_price_pence: float = 0.0
    grid_cost: float = 0.0
    customer_saving: float = 0.0
    om_cost: float = 0.0
    insurance_cost: float = 0.0
    audit_spv_cost: float = 0.0
    other_opex: float = 0.0
    inverter_reserve: float = 0.0
    total_opex: float = 0.0
    ebitda: float = 0.0
    capital_allowance: float = 0.0
    interest_expense: float = 0.0
    taxable_income: float = 0.0
    tax: float = 0.0
    cfads: float = 0.0
    debt_principal: float = 0.0
    debt_interest: float = 0.0
    debt_service: float = 0.0
    debt_balance_start: float = 0.0
    debt_balance_end: float = 0.0
    dscr: float = 0.0
    fcf_to_equity: float = 0.0
    shl_interest: float = 0.0
    shl_repayment: float = 0.0
    shl_balance_start: float = 0.0
    shl_balance_end: float = 0.0
    equity_distribution: float = 0.0
    cumulative_distributions: float = 0.0
    cumulative_shl: float = 0.0
    buyout_value: float = 0.0


@dataclass
class ModelResults:
    # Key dates
    cod: date = date(2026, 10, 1)
    construction_start: date = date(2026, 8, 1)
    construction_end: date = date(2026, 9, 30)
    financial_close: date = date(2026, 7, 31)
    operations_end: date = date(2051, 10, 31)
    first_indexation_date: date = date(2028, 4, 1)
    debt_end: date = date(2043, 9, 30)
    shl_end: date = date(2036, 9, 30)

    # Construction capex
    epc_total: float = 0.0
    insurance_construction: float = 0.0
    transaction_costs: float = 0.0
    transaction_costs_detailed: float = 0.0
    acquisition_costs: float = 0.0
    development_fee_total: float = 0.0
    development_fee_per_kwp: float = 0.0
    management_company_fee: float = 0.0
    stamp_duty: float = 0.0
    contingency: float = 0.0
    total_capex: float = 0.0

    # Generation
    annual_generation_kwh: float = 0.0

    # Target return
    credit_score_irr: float = 0.0
    ppa_uplift: float = 0.0
    target_irr: float = 0.0

    # Solved values
    ppa_rate_year1_pence: float = 0.0
    dev_fee_per_kwp_solved: float = 0.0
    dev_fee_total_solved: float = 0.0

    # Debt
    senior_debt_amount: float = 0.0
    equity_portion: float = 0.0
    shl_amount: float = 0.0
    pure_equity: float = 0.0

    # Returns
    levered_irr: float = 0.0
    unlevered_irr: float = 0.0
    cash_multiple: float = 0.0
    payback_year: int = 0
    average_dscr: float = 0.0

    # Customer outputs
    year1_saving: float = 0.0
    avg_annual_saving: float = 0.0
    total_lifetime_saving: float = 0.0
    avg_lifetime_ppa_rate: float = 0.0
    avg_lifetime_grid_rate: float = 0.0

    # Annual cashflows
    cashflows: list = field(default_factory=list)

    # Warnings
    warnings: list = field(default_factory=list)

    # LD outputs
    ld_per_1pct: float = 0.0
    ld_perf_cap_amount: float = 0.0
    ld_perf_pct_covered: float = 0.0
    ld_delay_per_day: float = 0.0
    ld_delay_cap_amount: float = 0.0
    ld_delay_days_covered: float = 0.0

    # Construction period
    construction_months: int = 2

    # Solve method used
    solve_method: str = ""


# ── Safe IRR Calculation ──────────────────────────────────────────────

def _safe_irr(cashflows: list) -> float:
    """Compute IRR with robust error handling."""
    if not cashflows or len(cashflows) < 2:
        return 0.0
    # Check there's at least one sign change
    has_neg = any(c < 0 for c in cashflows)
    has_pos = any(c > 0 for c in cashflows)
    if not (has_neg and has_pos):
        return 0.0
    try:
        irr_val = float(npf.irr(cashflows))
        if math.isnan(irr_val) or math.isinf(irr_val):
            return 0.0
        # Clamp to reasonable range
        return max(-0.99, min(irr_val, 5.0))
    except Exception:
        # Fallback: use brentq on NPV
        try:
            def npv_at_rate(r):
                return sum(c / (1 + r) ** i for i, c in enumerate(cashflows))
            return brentq(npv_at_rate, -0.5, 5.0, xtol=1e-6, maxiter=500)
        except Exception:
            return 0.0


# ── Core Model ───────────────────────────────────────────────────────

class PricingModel:

    def __init__(self, inputs: ModelInputs):
        self.inp = inputs

    def compute_dates(self) -> dict:
        inp = self.inp
        cod = first_of_month(inp.cod_date)
        cm = inp.effective_construction_months()
        construction_end = cod - timedelta(days=1)
        construction_start = first_of_month(add_months(cod, -cm))
        financial_close = end_of_month(add_months(construction_start, -1))
        operations_end = end_of_month(add_months(cod, inp.ppa_length_years * 12 - 1))
        debt_end = end_of_month(add_months(cod, inp.debt_tenor_years * 12 - 1))
        shl_end = end_of_month(add_months(cod, inp.shl_tenor_years * 12)) - timedelta(days=1)

        if cod.month >= 9:
            first_idx = date(cod.year + 2, 4, 1)
        else:
            first_idx = date(cod.year + 1, 4, 1)

        return {
            "cod": cod,
            "construction_start": construction_start,
            "construction_end": construction_end,
            "financial_close": financial_close,
            "operations_end": operations_end,
            "debt_end": debt_end,
            "shl_end": shl_end,
            "first_indexation_date": first_idx,
            "construction_months": cm,
        }

    def compute_capex(self, dev_fee_total: float) -> dict:
        inp = self.inp
        sz = inp.project_size_kwp

        epc_total = inp.epc_per_kwp * sz
        insurance_construction = inp.insurance_construction_per_kwp * sz
        transaction_costs = C.get_simplified_transaction_cost(sz)
        transaction_costs_detailed = C.get_detailed_transaction_cost(sz, is_rtb=True)
        acquisition_costs = inp.acquisition_costs

        sub = epc_total + insurance_construction + transaction_costs + acquisition_costs + dev_fee_total
        mgmt_fee = inp.management_company_fee_pct * sub
        stamp_duty = inp.stamp_duty_pct * (epc_total + dev_fee_total)
        contingency = inp.contingency_pct * epc_total

        total = epc_total + insurance_construction + transaction_costs + acquisition_costs + \
                dev_fee_total + mgmt_fee + stamp_duty + contingency

        return {
            "epc_total": epc_total,
            "insurance_construction": insurance_construction,
            "transaction_costs": transaction_costs,
            "transaction_costs_detailed": transaction_costs_detailed,
            "acquisition_costs": acquisition_costs,
            "development_fee_total": dev_fee_total,
            "management_company_fee": mgmt_fee,
            "stamp_duty": stamp_duty,
            "contingency": contingency,
            "total_capex": total,
        }

    def compute_annual_opex(self, year: int) -> dict:
        inp = self.inp
        sz = inp.project_size_kwp

        om = C.get_om_rate(sz) * sz
        insurance = C.INSURANCE_PER_KWP * sz
        audit_spv = C.get_audit_spv_rate(sz) * sz
        land = inp.land_lease
        biz_rates = inp.business_rates_per_kwp * sz
        asset_mgmt = inp.asset_management_per_kwp * sz
        elec_net = inp.elec_internet_metering_per_kwp * sz

        # Inverter replacement reserve
        inv_reserve = 0.0
        if inp.inverter_replacement_per_kwp > 0:
            start_yr = C.DEFAULTS["inverter_funding_start_year"]
            end_yr = C.DEFAULTS["inverter_funding_end_year"]
            if start_yr < year <= end_yr:
                funding_years = end_yr - start_yr
                inv_reserve = (inp.inverter_replacement_per_kwp * sz) / funding_years

        other = land + biz_rates + asset_mgmt + elec_net

        return {
            "om_cost": om,
            "insurance_cost": insurance,
            "audit_spv_cost": audit_spv,
            "other_opex": other,
            "inverter_reserve": inv_reserve,
            "total_opex": om + insurance + audit_spv + other + inv_reserve,
        }

    def run_full_model(self, ppa_rate_pence: float, dev_fee_total: float) -> ModelResults:
        """Run the complete financial model for given PPA rate and dev fee."""
        inp = self.inp
        res = ModelResults()

        # ── Dates ──
        dates = self.compute_dates()
        res.cod = dates["cod"]
        res.construction_start = dates["construction_start"]
        res.construction_end = dates["construction_end"]
        res.financial_close = dates["financial_close"]
        res.operations_end = dates["operations_end"]
        res.debt_end = dates["debt_end"]
        res.shl_end = dates["shl_end"]
        res.first_indexation_date = dates["first_indexation_date"]
        res.construction_months = dates["construction_months"]
        res.solve_method = inp.solve_method

        # ── Generation ──
        base_annual_gen = inp.project_size_kwp * inp.specific_yield
        res.annual_generation_kwh = base_annual_gen

        # ── Capex ──
        capex = self.compute_capex(dev_fee_total)
        res.epc_total = capex["epc_total"]
        res.insurance_construction = capex["insurance_construction"]
        res.transaction_costs = capex["transaction_costs"]
        res.transaction_costs_detailed = capex["transaction_costs_detailed"]
        res.acquisition_costs = capex["acquisition_costs"]
        res.development_fee_total = capex["development_fee_total"]
        res.development_fee_per_kwp = dev_fee_total / inp.project_size_kwp if inp.project_size_kwp > 0 else 0
        res.management_company_fee = capex["management_company_fee"]
        res.stamp_duty = capex["stamp_duty"]
        res.contingency = capex["contingency"]
        res.total_capex = capex["total_capex"]

        # ── Solved values ──
        res.ppa_rate_year1_pence = ppa_rate_pence
        res.dev_fee_per_kwp_solved = res.development_fee_per_kwp
        res.dev_fee_total_solved = dev_fee_total

        # ── Target IRR ──
        res.credit_score_irr = lookup_credit_score_irr(inp.credit_score)
        res.ppa_uplift = lookup_ppa_uplift(ppa_rate_pence)
        res.target_irr = res.credit_score_irr + res.ppa_uplift

        # ── Debt & Equity ──
        res.senior_debt_amount = inp.debt_gearing * res.total_capex
        res.equity_portion = res.total_capex - res.senior_debt_amount
        shl_ltv = 1.0 - inp.equity_ltv
        res.shl_amount = shl_ltv * res.equity_portion
        res.pure_equity = inp.equity_ltv * res.equity_portion

        # ── Inflation / indexation ──
        if inp.ppa_indexation == "Fixed":
            inflation = inp.fixed_inflation_rate
        else:
            inflation = inp.assumed_inflation_rate

        # Years from COD to first indexation
        first_idx_year = res.first_indexation_date.year - res.cod.year

        # ── Capital allowances ──
        if inp.capital_allowance_method == "DB":
            ca_rate = inp.capital_allowance_rate
        else:
            ca_rate = 1.0 / max(1, inp.ppa_length_years)

        ca_pool = res.total_capex  # simplified: full capex qualifies

        # ── Debt schedule setup ──
        debt_balance = res.senior_debt_amount
        moratorium_years = max(0, math.ceil(inp.capital_moratorium_months / 12))
        debt_end_year = inp.debt_tenor_years

        # Annuity payment calculation (for years after moratorium)
        active_repayment_years = debt_end_year - moratorium_years
        if active_repayment_years > 0 and inp.repayment_method == "Annuity":
            annuity_payment = npf.pmt(inp.debt_interest_rate, active_repayment_years,
                                      -res.senior_debt_amount)
        else:
            annuity_payment = 0.0

        # ── SHL schedule ──
        shl_balance = res.shl_amount
        shl_annual_repayment = res.shl_amount / max(1, inp.shl_tenor_years) if inp.shl_tenor_years > 0 else 0

        # ── Cashflow arrays ──
        n_years = inp.ppa_length_years
        cashflows = []
        cumulative_dist = 0.0
        cumulative_shl_paid = 0.0
        # Levered IRR: total equity invested (pure equity + SHL) vs all returns to equity holders
        total_equity_invested = res.pure_equity + res.shl_amount
        equity_cfs = [-total_equity_invested]  # Year 0
        project_cfs = [-res.total_capex]  # Year 0

        total_ppa_weighted = 0.0
        total_grid_weighted = 0.0
        total_gen = 0.0
        total_saving = 0.0

        dscr_values = []

        for yr in range(1, n_years + 1):
            cf = YearCashflow(year=yr, year_label=f"Year {yr}")

            # Generation with degradation
            degradation_factor = (1 - inp.annual_degradation) ** (yr - 1)
            cf.generation_kwh = base_annual_gen * degradation_factor

            # PPA price with escalation
            if yr == 1:
                cf.ppa_price_pence = ppa_rate_pence
            else:
                if yr < first_idx_year:
                    cf.ppa_price_pence = ppa_rate_pence
                else:
                    years_of_escalation = yr - first_idx_year + 1
                    cf.ppa_price_pence = ppa_rate_pence * (1 + inflation) ** years_of_escalation

            # Revenue (pence to pounds)
            cf.revenue = cf.generation_kwh * cf.ppa_price_pence / 100.0

            # Take-or-pay: ensure minimum revenue
            if inp.take_or_pay_method == "% of Year 1 Generation (fixed kWh)":
                min_gen = inp.take_or_pay_pct * base_annual_gen
            else:  # % of Generation
                min_gen = inp.take_or_pay_pct * cf.generation_kwh
            min_revenue = min_gen * cf.ppa_price_pence / 100.0
            cf.revenue = max(cf.revenue, min_revenue)

            # Grid price for comparison
            cf.grid_price_pence = inp.grid_price_pence * (1 + inp.grid_price_escalation) ** (yr - 1)
            cf.grid_cost = cf.generation_kwh * cf.grid_price_pence / 100.0
            cf.customer_saving = cf.grid_cost - cf.revenue

            # Track for averages
            total_ppa_weighted += cf.ppa_price_pence * cf.generation_kwh
            total_grid_weighted += cf.grid_price_pence * cf.generation_kwh
            total_gen += cf.generation_kwh
            total_saving += cf.customer_saving

            # Opex
            opex = self.compute_annual_opex(yr)
            cf.om_cost = opex["om_cost"]
            cf.insurance_cost = opex["insurance_cost"]
            cf.audit_spv_cost = opex["audit_spv_cost"]
            cf.other_opex = opex["other_opex"]
            cf.inverter_reserve = opex["inverter_reserve"]
            cf.total_opex = opex["total_opex"]

            # EBITDA
            cf.ebitda = cf.revenue - cf.total_opex

            # Capital allowances
            if inp.capital_allowance_method == "DB":
                cf.capital_allowance = ca_pool * ca_rate
                ca_pool -= cf.capital_allowance
                ca_pool = max(0, ca_pool)
            else:
                cf.capital_allowance = res.total_capex * ca_rate

            # Debt interest
            cf.debt_balance_start = debt_balance
            cf.debt_interest = debt_balance * inp.debt_interest_rate

            # Interest expense for tax
            cf.interest_expense = cf.debt_interest

            # Taxable income
            cf.taxable_income = cf.ebitda - cf.capital_allowance - cf.interest_expense
            cf.tax = max(0.0, cf.taxable_income * inp.tax_rate)

            # CFADS
            cf.cfads = cf.ebitda - cf.tax

            # Debt service
            if yr <= debt_end_year and debt_balance > 0:
                cf.debt_interest = debt_balance * inp.debt_interest_rate

                if yr <= moratorium_years:
                    # Interest only during moratorium
                    cf.debt_principal = 0.0
                elif inp.repayment_method == "Annuity":
                    cf.debt_principal = max(0, annuity_payment - cf.debt_interest)
                    cf.debt_principal = min(cf.debt_principal, debt_balance)
                else:
                    # DSCR target method
                    if inp.dscr_target > 0:
                        max_debt_service = cf.cfads / inp.dscr_target
                        cf.debt_principal = max(0, max_debt_service - cf.debt_interest)
                        cf.debt_principal = min(cf.debt_principal, debt_balance)
                    else:
                        cf.debt_principal = 0.0

                cf.debt_service = cf.debt_interest + cf.debt_principal
                debt_balance -= cf.debt_principal
            else:
                cf.debt_interest = 0.0
                cf.debt_principal = 0.0
                cf.debt_service = 0.0

            cf.debt_balance_end = max(0, debt_balance)

            # DSCR
            if cf.debt_service > 0:
                cf.dscr = cf.cfads / cf.debt_service
                dscr_values.append(cf.dscr)
            else:
                cf.dscr = 0.0

            # Free cash flow to equity
            cf.fcf_to_equity = cf.cfads - cf.debt_service

            # SHL
            cf.shl_balance_start = shl_balance
            if yr <= inp.shl_tenor_years and shl_balance > 0:
                cf.shl_interest = shl_balance * inp.shl_coupon
                cf.shl_repayment = min(shl_annual_repayment, shl_balance)
                shl_balance -= cf.shl_repayment
            else:
                cf.shl_interest = 0.0
                cf.shl_repayment = 0.0
            cf.shl_balance_end = max(0, shl_balance)

            # Equity distribution
            shl_total = cf.shl_interest + cf.shl_repayment
            cf.equity_distribution = max(0, cf.fcf_to_equity - shl_total)
            cumulative_dist += cf.equity_distribution
            cumulative_shl_paid += shl_total
            cf.cumulative_distributions = cumulative_dist
            cf.cumulative_shl = cumulative_shl_paid

            # Buyout value: NPV of remaining cashflows discounted at target IRR
            # Simplified: remaining revenue stream discounted
            remaining_years = n_years - yr
            if remaining_years > 0 and res.target_irr > 0:
                # Approximate buyout as NPV of remaining EBITDA
                future_ebitda = cf.ebitda * ((1 - (1 + inflation) ** remaining_years *
                                              (1 + res.target_irr) ** (-remaining_years)) /
                                             (res.target_irr - inflation)) if abs(res.target_irr - inflation) > 0.001 \
                    else cf.ebitda * remaining_years
                cf.buyout_value = max(0, future_ebitda)
            else:
                cf.buyout_value = 0.0

            # IRR cash flows
            equity_cfs.append(cf.equity_distribution + cf.shl_interest + cf.shl_repayment)
            project_cfs.append(cf.cfads)

            cashflows.append(cf)

        res.cashflows = cashflows

        # ── Compute IRR ──
        # Use a safe IRR wrapper that handles edge cases
        res.levered_irr = _safe_irr(equity_cfs)
        res.unlevered_irr = _safe_irr(project_cfs)

        # ── Cash multiple ──
        total_equity_return = sum(cf.equity_distribution + cf.shl_interest + cf.shl_repayment
                                  for cf in cashflows)
        if total_equity_invested > 0:
            res.cash_multiple = total_equity_return / total_equity_invested
        else:
            res.cash_multiple = 0.0

        # ── Payback ──
        cum = 0.0
        res.payback_year = n_years
        for cf in cashflows:
            cum += cf.equity_distribution + cf.shl_interest + cf.shl_repayment
            if cum >= total_equity_invested:
                res.payback_year = cf.year
                break

        # ── Average DSCR ──
        if dscr_values:
            res.average_dscr = sum(dscr_values) / len(dscr_values)

        # ── Customer outputs ──
        if cashflows:
            res.year1_saving = cashflows[0].customer_saving
        res.avg_annual_saving = total_saving / n_years if n_years > 0 else 0
        res.total_lifetime_saving = total_saving
        res.avg_lifetime_ppa_rate = total_ppa_weighted / total_gen if total_gen > 0 else 0
        res.avg_lifetime_grid_rate = total_grid_weighted / total_gen if total_gen > 0 else 0

        # ── Liquidated Damages ──
        if inp.ld_total_amount_paid != 0 and inp.ld_performance_change_pct != 0:
            res.ld_per_1pct = abs(inp.ld_total_amount_paid / (inp.ld_performance_change_pct * 100))
        res.ld_perf_cap_amount = inp.ld_performance_cap_pct * inp.epc_per_kwp * inp.project_size_kwp
        if res.ld_per_1pct > 0:
            res.ld_perf_pct_covered = res.ld_perf_cap_amount / res.ld_per_1pct

        ppa_pounds = ppa_rate_pence / 100.0
        res.ld_delay_per_day = (base_annual_gen * ppa_pounds * inp.peak_seasonality_factor) / 30.0
        res.ld_delay_cap_amount = inp.ld_delay_cap_pct * inp.epc_per_kwp * inp.project_size_kwp
        if res.ld_delay_per_day > 0:
            res.ld_delay_days_covered = res.ld_delay_cap_amount / res.ld_delay_per_day

        # ── Warnings ──
        if ppa_rate_pence >= C.PPA_HIGH_WARNING_PENCE:
            res.warnings.append(
                f"PPA price is {ppa_rate_pence:.1f} p/kWh (≥18p). Contact ADE — price is unusually high."
            )

        tc_diff = abs(capex["transaction_costs"] - capex["transaction_costs_detailed"])
        if tc_diff > 5000:
            res.warnings.append(
                f"Simplified transaction cost (£{capex['transaction_costs']:,.0f}) differs from detailed "
                f"estimate (£{capex['transaction_costs_detailed']:,.0f}) by £{tc_diff:,.0f}."
            )

        if inp.take_or_pay_pct < 0.5:
            res.warnings.append(
                "Take-or-Pay is below 50%. Check that consumption assumptions are reasonable."
            )

        return res

    def solve(self) -> ModelResults:
        """
        Main entry point: solve for either PPA Rate or Dev Fee to hit target IRR.
        Mirrors the VBA solver logic: iterate until |Model IRR - Target IRR| < 0.0001
        """
        inp = self.inp

        if inp.solve_method == "PPA Rate":
            return self._solve_ppa_rate()
        else:
            return self._solve_dev_fee()

    def _solve_ppa_rate(self) -> ModelResults:
        """Iterate PPA rate until levered IRR = target IRR."""
        inp = self.inp
        dev_fee_total = inp.dev_fee_per_kwp * inp.project_size_kwp

        def irr_error(ppa_pence):
            # Target IRR depends on PPA price (uplift), so recompute each iteration
            t_irr = compute_target_irr(inp.credit_score, ppa_pence)
            result = self.run_full_model(ppa_pence, dev_fee_total)
            return result.levered_irr - t_irr

        # Find bracket: low PPA → high IRR (under-target), high PPA → low IRR (over-target)
        # Actually: higher PPA → more revenue → higher IRR.
        # But higher PPA also increases target IRR via uplift table.
        # At very low PPA, IRR < target (negative). At some PPA, IRR = target.
        # At very high PPA, IRR > target.
        # So irr_error goes from negative (low PPA) to positive (high PPA).

        # Use initial guess from VBA: start at 12p
        lo, hi = 2.0, 45.0

        # Verify bracket
        err_lo = irr_error(lo)
        err_hi = irr_error(hi)

        if err_lo * err_hi > 0:
            # No bracket - try wider range
            lo, hi = 0.5, 50.0
            err_lo = irr_error(lo)
            err_hi = irr_error(hi)

        try:
            if err_lo * err_hi <= 0:
                solved_ppa = brentq(irr_error, lo, hi, xtol=0.005, maxiter=300)
            else:
                solved_ppa = self._golden_section_search(irr_error, lo, hi, 0.005)
        except (ValueError, RuntimeError):
            solved_ppa = self._golden_section_search(irr_error, lo, hi, 0.005)

        result = self.run_full_model(solved_ppa, dev_fee_total)
        result.ppa_rate_year1_pence = solved_ppa
        result.dev_fee_per_kwp_solved = inp.dev_fee_per_kwp
        result.dev_fee_total_solved = dev_fee_total
        return result

    def _solve_dev_fee(self) -> ModelResults:
        """Iterate dev fee until levered IRR = target IRR."""
        inp = self.inp
        ppa_pence = inp.ppa_price_input_pence
        target_irr = compute_target_irr(inp.credit_score, ppa_pence)

        def irr_error(dev_fee_total):
            result = self.run_full_model(ppa_pence, dev_fee_total)
            return result.levered_irr - target_irr

        # Higher dev fee → higher capex → lower IRR (negative error)
        # Lower dev fee → lower capex → higher IRR (positive error)
        lo, hi = 0.0, 3000.0 * inp.project_size_kwp

        err_lo = irr_error(lo)
        err_hi = irr_error(hi)

        try:
            if err_lo * err_hi <= 0:
                solved_fee = brentq(irr_error, lo, hi, xtol=50, maxiter=300)
            else:
                solved_fee = self._golden_section_search(irr_error, lo, hi, 50)
        except (ValueError, RuntimeError):
            solved_fee = self._golden_section_search(irr_error, lo, hi, 50)

        result = self.run_full_model(ppa_pence, solved_fee)
        result.ppa_rate_year1_pence = ppa_pence
        result.dev_fee_per_kwp_solved = solved_fee / inp.project_size_kwp if inp.project_size_kwp > 0 else 0
        result.dev_fee_total_solved = solved_fee
        return result

    @staticmethod
    def _golden_section_search(func, lo, hi, tol):
        """Find x where |func(x)| is minimised (fallback when brentq can't bracket)."""
        best_x = (lo + hi) / 2
        best_err = abs(func(best_x))

        # Binary search minimising absolute error
        for _ in range(500):
            if (hi - lo) < tol * 0.001:
                break
            mid = (lo + hi) / 2
            val = func(mid)
            if abs(val) < best_err:
                best_x = mid
                best_err = abs(val)
            if abs(val) < 0.0001:
                return mid
            if val > 0:
                hi = mid
            else:
                lo = mid
        return best_x
