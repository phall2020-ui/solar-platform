"""
AMPYR Distributed Energy - Pricing Calculator GUI
==================================================
Branded desktop interface using customtkinter with AMPYR colour scheme.
"""

import os
import sys
import threading
import math
from datetime import date, datetime
from typing import Optional

import customtkinter as ctk

from . import constants as C
from .engine import ModelInputs, PricingModel, ModelResults


# ── Theme Setup ──────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def _resource_path(relative: str) -> str:
    """Resolve path for PyInstaller bundled resources."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


# ── Scrollable Input Frame ───────────────────────────────────────────

class ScrollableInputFrame(ctk.CTkScrollableFrame):
    """Scrollable container for all input fields."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.entries = {}
        self.dropdowns = {}
        self._row = 0

    # ── helpers ──

    def _add_section(self, title: str):
        lbl = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                           text_color=C.BRAND_TEAL)
        lbl.grid(row=self._row, column=0, columnspan=3, padx=10, pady=(18, 6), sticky="w")
        sep = ctk.CTkFrame(self, height=1, fg_color=C.BRAND_TEAL_DARK)
        sep.grid(row=self._row + 1, column=0, columnspan=3, padx=10, sticky="ew")
        self._row += 2

    def _add_entry(self, key: str, label: str, default, unit: str = "",
                   width: int = 140, tooltip: str = ""):
        lbl = ctk.CTkLabel(self, text=label, anchor="w")
        lbl.grid(row=self._row, column=0, padx=(10, 5), pady=3, sticky="w")
        ent = ctk.CTkEntry(self, width=width, justify="right")
        ent.insert(0, str(default))
        ent.grid(row=self._row, column=1, padx=5, pady=3, sticky="w")
        if unit:
            u = ctk.CTkLabel(self, text=unit, text_color=C.BRAND_GREY, anchor="w",
                             font=ctk.CTkFont(size=11))
            u.grid(row=self._row, column=2, padx=(2, 10), pady=3, sticky="w")
        self.entries[key] = ent
        self._row += 1

    def _add_dropdown(self, key: str, label: str, values: list, default: str):
        lbl = ctk.CTkLabel(self, text=label, anchor="w")
        lbl.grid(row=self._row, column=0, padx=(10, 5), pady=3, sticky="w")
        dd = ctk.CTkOptionMenu(self, values=values, width=160,
                                fg_color=C.BRAND_NAVY_MID,
                                button_color=C.BRAND_TEAL_DARK,
                                button_hover_color=C.BRAND_TEAL)
        dd.set(default)
        dd.grid(row=self._row, column=1, padx=5, pady=3, sticky="w")
        self.dropdowns[key] = dd
        self._row += 1

    def _add_checkbox(self, key: str, label: str, default: bool):
        var = ctk.BooleanVar(value=default)
        cb = ctk.CTkCheckBox(self, text=label, variable=var,
                              fg_color=C.BRAND_TEAL, hover_color=C.BRAND_TEAL_DARK)
        cb.grid(row=self._row, column=0, columnspan=2, padx=10, pady=3, sticky="w")
        self.entries[key] = var
        self._row += 1

    def _add_date_entry(self, key: str, label: str, default: date):
        lbl = ctk.CTkLabel(self, text=label, anchor="w")
        lbl.grid(row=self._row, column=0, padx=(10, 5), pady=3, sticky="w")
        ent = ctk.CTkEntry(self, width=140, justify="right",
                           placeholder_text="DD/MM/YYYY")
        ent.insert(0, default.strftime("%d/%m/%Y"))
        ent.grid(row=self._row, column=1, padx=5, pady=3, sticky="w")
        u = ctk.CTkLabel(self, text="DD/MM/YYYY", text_color=C.BRAND_GREY, anchor="w",
                         font=ctk.CTkFont(size=11))
        u.grid(row=self._row, column=2, padx=(2, 10), pady=3, sticky="w")
        self.entries[key] = ent
        self._row += 1

    # ── Build form ──

    def build(self):
        self.grid_columnconfigure(0, weight=1, minsize=220)
        self.grid_columnconfigure(1, weight=0, minsize=160)
        self.grid_columnconfigure(2, weight=0, minsize=80)

        D = C.DEFAULTS

        # ── Project Details ──
        self._add_section("PROJECT DETAILS")
        self._add_entry("project_name", "Project Name", D["project_name"])
        self._add_date_entry("cod_date", "COD / Acquisition Date", date(2026, 10, 1))
        self._add_entry("credit_score", "Customer Credit Score", D["credit_score"], "(0–100)")
        self._add_entry("project_size", "Project Size", D["project_size_kwp"], "kWp")
        self._add_entry("specific_yield", "Specific Yield", D["specific_yield"], "kWh/kWp")
        self._add_entry("epc_price", "EPC / Acquisition Price", D["epc_per_kwp"], "£/kWp")
        self._add_entry("construction_months", "Construction Period",
                        "", "months (blank=auto)")

        # ── PPA Terms ──
        self._add_section("PPA TERMS")
        self._add_entry("ppa_length", "PPA Length", D["ppa_length_years"], "years")
        self._add_dropdown("ppa_indexation", "PPA Indexation", ["RPI", "CPI", "Fixed"],
                           D["ppa_indexation"])
        self._add_entry("fixed_inflation", "Fixed Inflation Rate", "2.5", "%")
        self._add_entry("assumed_inflation", "Assumed Inflation (RPI/CPI)", "2.5", "%")
        self._add_entry("take_or_pay", "Take or Pay", "80", "%")
        self._add_dropdown("top_method", "Take or Pay Method",
                           ["% of Generation", "% of Year 1 Generation (fixed kWh)"],
                           D["take_or_pay_method"])

        # ── Solve Settings ──
        self._add_section("SOLVE SETTINGS")
        self._add_dropdown("solve_method", "Solve Method", ["PPA Rate", "Dev Fee"],
                           D["solve_method"])
        self._add_entry("ppa_price_input", "Year 1 PPA Price (Dev Fee mode)",
                        D["ppa_price_input"], "p/kWh")
        self._add_entry("dev_fee_input", "Development Fee (PPA Rate mode)",
                        D["dev_fee_per_kwp"], "£/kWp")

        # ── Customer Comparison ──
        self._add_section("CUSTOMER COMPARISON")
        self._add_entry("grid_price", "Grid Electricity Price", D["grid_price_pence"], "p/kWh")
        self._add_entry("grid_escalation", "Grid Price Escalation", "3.0", "% p.a.")

        # ── Financing ──
        self._add_section("FINANCING")
        self._add_entry("debt_gearing", "Debt Gearing", "70", "%")
        self._add_entry("debt_rate", "Debt Interest Rate", "6.0", "%")
        self._add_entry("debt_tenor", "Debt Tenor", D["debt_tenor_years"], "years")
        self._add_dropdown("repayment_method", "Repayment Method",
                           ["Annuity", "DSCR Target"], D["repayment_method"])
        self._add_entry("dscr_target", "DSCR Target", D["dscr_target"], "x")
        self._add_entry("equity_ltv", "Equity LTV", "30", "%")
        self._add_entry("shl_coupon", "SHL Coupon", "8.0", "%")
        self._add_entry("shl_tenor", "SHL Tenor", D["shl_tenor_years"], "years")
        self._add_checkbox("warehousing", "Warehousing Facility Active",
                           D["warehousing_active"])

        # ── Costs & Opex ──
        self._add_section("COSTS & OPEX")
        self._add_entry("stamp_duty", "Stamp Duty", "0.5", "%")
        self._add_entry("contingency", "Contingency", "5.0", "%")
        self._add_entry("mgmt_fee", "Management Company Fee", "3.0", "%")
        self._add_entry("insurance_constr", "Insurance (Construction)",
                        D["insurance_construction_per_kwp"], "£/kWp")
        self._add_entry("asset_mgmt", "Asset Management",
                        D["asset_management_per_kwp"], "£/kWp/yr")
        self._add_entry("biz_rates", "Business Rates",
                        D["business_rates_per_kwp"], "£/kWp/yr")
        self._add_entry("degradation", "Annual Degradation", "0.5", "%")

        # ── Tax ──
        self._add_section("TAX & CAPITAL ALLOWANCES")
        self._add_entry("tax_rate", "Corporation Tax Rate", "25", "%")
        self._add_dropdown("ca_method", "Capital Allowance Method",
                           ["DB", "Straight Line"], D["capital_allowance_method"])
        self._add_entry("ca_rate", "Capital Allowance Rate", "6.0", "%")

    # ── Collect inputs ──

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.entries[key].get())
        except (ValueError, AttributeError):
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            val = self.entries[key].get().strip()
            if val == "":
                return default
            return int(float(val))
        except (ValueError, AttributeError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        try:
            return self.entries[key].get().strip()
        except AttributeError:
            return default

    def get_bool(self, key: str) -> bool:
        try:
            return self.entries[key].get()
        except (AttributeError, KeyError):
            return False

    def get_dropdown(self, key: str) -> str:
        try:
            return self.dropdowns[key].get()
        except KeyError:
            return ""

    def get_date(self, key: str, default: date = date(2026, 10, 1)) -> date:
        try:
            txt = self.entries[key].get().strip()
            return datetime.strptime(txt, "%d/%m/%Y").date()
        except (ValueError, AttributeError):
            return default

    def collect_inputs(self) -> ModelInputs:
        """Gather all form values into a ModelInputs dataclass."""
        cm_raw = self.get_str("construction_months")
        cm = int(float(cm_raw)) if cm_raw else None

        return ModelInputs(
            project_name=self.get_str("project_name", "New Solar Project"),
            cod_date=self.get_date("cod_date"),
            construction_months=cm,
            credit_score=self.get_int("credit_score", 80),
            project_size_kwp=self.get_float("project_size", 500),
            specific_yield=self.get_float("specific_yield", 950),
            epc_per_kwp=self.get_float("epc_price", 650),
            ppa_length_years=self.get_int("ppa_length", 25),
            ppa_indexation=self.get_dropdown("ppa_indexation"),
            fixed_inflation_rate=self.get_float("fixed_inflation", 2.5) / 100,
            assumed_inflation_rate=self.get_float("assumed_inflation", 2.5) / 100,
            take_or_pay_pct=self.get_float("take_or_pay", 80) / 100,
            take_or_pay_method=self.get_dropdown("top_method"),
            solve_method=self.get_dropdown("solve_method"),
            ppa_price_input_pence=self.get_float("ppa_price_input", 10),
            dev_fee_per_kwp=self.get_float("dev_fee_input", 100),
            grid_price_pence=self.get_float("grid_price", 30),
            grid_price_escalation=self.get_float("grid_escalation", 3.0) / 100,
            debt_gearing=self.get_float("debt_gearing", 70) / 100,
            debt_interest_rate=self.get_float("debt_rate", 6.0) / 100,
            debt_tenor_years=self.get_int("debt_tenor", 17),
            repayment_method=self.get_dropdown("repayment_method"),
            dscr_target=self.get_float("dscr_target", 1.30),
            equity_ltv=self.get_float("equity_ltv", 30) / 100,
            shl_coupon=self.get_float("shl_coupon", 8.0) / 100,
            shl_tenor_years=self.get_int("shl_tenor", 10),
            warehousing_active=self.get_bool("warehousing"),
            insurance_construction_per_kwp=self.get_float("insurance_constr", 5),
            stamp_duty_pct=self.get_float("stamp_duty", 0.5) / 100,
            contingency_pct=self.get_float("contingency", 5.0) / 100,
            management_company_fee_pct=self.get_float("mgmt_fee", 3.0) / 100,
            asset_management_per_kwp=self.get_float("asset_mgmt", 3.0),
            business_rates_per_kwp=self.get_float("biz_rates", 0),
            annual_degradation=self.get_float("degradation", 0.5) / 100,
            tax_rate=self.get_float("tax_rate", 25) / 100,
            capital_allowance_method=self.get_dropdown("ca_method"),
            capital_allowance_rate=self.get_float("ca_rate", 6.0) / 100,
        )


# ── Results Display Frame ────────────────────────────────────────────

class ResultsFrame(ctk.CTkScrollableFrame):
    """Scrollable results display with formatted output."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._widgets = []

    def clear(self):
        for w in self._widgets:
            w.destroy()
        self._widgets = []

    def _add_header(self, text: str):
        lbl = ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=15, weight="bold"),
                           text_color=C.BRAND_TEAL)
        lbl.pack(anchor="w", padx=12, pady=(14, 2))
        sep = ctk.CTkFrame(self, height=1, fg_color=C.BRAND_TEAL_DARK)
        sep.pack(fill="x", padx=12, pady=(0, 6))
        self._widgets.extend([lbl, sep])

    def _add_row(self, label: str, value: str, highlight: bool = False,
                 warning: bool = False):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=1)

        color = C.BRAND_WHITE
        if highlight:
            color = C.BRAND_TEAL
        if warning:
            color = C.BRAND_RED_WARNING

        l = ctk.CTkLabel(row, text=label, anchor="w", width=280,
                         font=ctk.CTkFont(size=12))
        l.pack(side="left")
        v = ctk.CTkLabel(row, text=value, anchor="e", text_color=color,
                         font=ctk.CTkFont(size=12, weight="bold" if highlight else "normal"))
        v.pack(side="right", padx=(0, 10))
        self._widgets.extend([row, l, v])

    def _add_warning(self, text: str):
        frame = ctk.CTkFrame(self, fg_color="#3D1010", corner_radius=6)
        frame.pack(fill="x", padx=12, pady=4)
        lbl = ctk.CTkLabel(frame, text=f"⚠  {text}", text_color=C.BRAND_RED_WARNING,
                           font=ctk.CTkFont(size=11), wraplength=500, anchor="w",
                           justify="left")
        lbl.pack(padx=10, pady=6, anchor="w")
        self._widgets.extend([frame, lbl])

    def display(self, res: ModelResults, inputs: ModelInputs):
        self.clear()

        # ── Warnings ──
        if res.warnings:
            self._add_header("WARNINGS")
            for w in res.warnings:
                self._add_warning(w)

        # ── Key Results ──
        self._add_header("KEY RESULTS")
        self._add_row("Solve Method", res.solve_method)
        self._add_row("Year 1 PPA Rate", f"{res.ppa_rate_year1_pence:.2f} p/kWh", highlight=True)
        self._add_row("Development Fee", f"£{res.dev_fee_total_solved:,.0f}  "
                       f"(£{res.dev_fee_per_kwp_solved:,.1f}/kWp)", highlight=True)
        self._add_row("Levered IRR", f"{res.levered_irr * 100:.2f}%", highlight=True)
        self._add_row("Target IRR", f"{res.target_irr * 100:.2f}%")
        self._add_row("Unlevered IRR", f"{res.unlevered_irr * 100:.2f}%")
        self._add_row("Cash Multiple", f"{res.cash_multiple:.2f}x")
        self._add_row("Payback Period", f"Year {res.payback_year}")
        self._add_row("Average DSCR", f"{res.average_dscr:.2f}x")

        # ── Key Dates ──
        self._add_header("KEY DATES")
        self._add_row("Financial Close", res.financial_close.strftime("%d %b %Y"))
        self._add_row("Construction Start", res.construction_start.strftime("%d %b %Y"))
        self._add_row("Construction End", res.construction_end.strftime("%d %b %Y"))
        self._add_row("COD", res.cod.strftime("%d %b %Y"))
        self._add_row("Operations End", res.operations_end.strftime("%d %b %Y"))
        self._add_row("First Indexation", res.first_indexation_date.strftime("%d %b %Y"))
        self._add_row("Senior Debt Maturity", res.debt_end.strftime("%d %b %Y"))

        # ── Capex Breakdown ──
        self._add_header("CAPITAL EXPENDITURE")
        self._add_row("EPC Total", f"£{res.epc_total:,.0f}")
        self._add_row("Insurance (Construction)", f"£{res.insurance_construction:,.0f}")
        self._add_row("Transaction Costs", f"£{res.transaction_costs:,.0f}")
        self._add_row("Development Fee", f"£{res.development_fee_total:,.0f}")
        self._add_row("Management Company Fee", f"£{res.management_company_fee:,.0f}")
        self._add_row("Stamp Duty", f"£{res.stamp_duty:,.0f}")
        self._add_row("Contingency", f"£{res.contingency:,.0f}")
        self._add_row("Total Capex", f"£{res.total_capex:,.0f}", highlight=True)

        # ── Funding ──
        self._add_header("FUNDING STRUCTURE")
        self._add_row("Senior Debt", f"£{res.senior_debt_amount:,.0f}  "
                       f"({inputs.debt_gearing * 100:.0f}%)")
        self._add_row("SHL", f"£{res.shl_amount:,.0f}")
        self._add_row("Pure Equity", f"£{res.pure_equity:,.0f}")

        # ── Generation ──
        self._add_header("GENERATION")
        self._add_row("Annual Output (Year 1)", f"{res.annual_generation_kwh:,.0f} kWh")
        self._add_row("Project Size", f"{inputs.project_size_kwp:,.1f} kWp")
        self._add_row("Specific Yield", f"{inputs.specific_yield:,.0f} kWh/kWp")

        # ── Customer Savings ──
        self._add_header("CUSTOMER SAVINGS")
        self._add_row("Year 1 Saving", f"£{res.year1_saving:,.0f}", highlight=True)
        self._add_row("Average Annual Saving", f"£{res.avg_annual_saving:,.0f}")
        self._add_row("Total Lifetime Saving", f"£{res.total_lifetime_saving:,.0f}",
                       highlight=True)
        self._add_row("Avg Lifetime PPA Rate", f"{res.avg_lifetime_ppa_rate:.2f} p/kWh")
        self._add_row("Avg Lifetime Grid Rate", f"{res.avg_lifetime_grid_rate:.2f} p/kWh")


# ── Main Application Window ─────────────────────────────────────────

class PricingApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("AMPYR Distributed Energy — Solar PPA Pricing Calculator")
        self.geometry("1280x860")
        self.minsize(1000, 700)
        self.configure(fg_color=C.BRAND_NAVY)

        self._result: Optional[ModelResults] = None
        self._inputs: Optional[ModelInputs] = None

        self._build_ui()

    def _build_ui(self):
        # ── Header Bar ──
        header = ctk.CTkFrame(self, height=60, fg_color=C.BRAND_NAVY, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # AMPYR logo text
        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=20, pady=10)

        # Teal accent bar (mimics the logo chevron)
        accent = ctk.CTkFrame(logo_frame, width=4, height=35, fg_color=C.BRAND_TEAL,
                               corner_radius=2)
        accent.pack(side="left", padx=(0, 10))

        title_lbl = ctk.CTkLabel(logo_frame, text="AMPYR",
                                  font=ctk.CTkFont(family="Arial", size=24, weight="bold"),
                                  text_color=C.BRAND_WHITE)
        title_lbl.pack(side="left")

        divider = ctk.CTkLabel(logo_frame, text="  |  ",
                                font=ctk.CTkFont(size=24),
                                text_color=C.BRAND_GREY)
        divider.pack(side="left")

        subtitle = ctk.CTkLabel(logo_frame, text="DISTRIBUTED ENERGY",
                                 font=ctk.CTkFont(family="Arial", size=13),
                                 text_color=C.BRAND_GREY_LIGHT)
        subtitle.pack(side="left", pady=(4, 0))

        # App title on right
        app_title = ctk.CTkLabel(header, text="Solar PPA Pricing Calculator",
                                  font=ctk.CTkFont(size=14),
                                  text_color=C.BRAND_TEAL_LIGHT)
        app_title.pack(side="right", padx=20)

        # ── Header separator ──
        sep = ctk.CTkFrame(self, height=2, fg_color=C.BRAND_TEAL, corner_radius=0)
        sep.pack(fill="x")

        # ── Main content ──
        content = ctk.CTkFrame(self, fg_color=C.BRAND_NAVY)
        content.pack(fill="both", expand=True, padx=0, pady=0)
        content.grid_columnconfigure(0, weight=2, minsize=480)
        content.grid_columnconfigure(1, weight=3, minsize=500)
        content.grid_rowconfigure(0, weight=1)

        # ── Left panel: Inputs ──
        left = ctk.CTkFrame(content, fg_color=C.BRAND_NAVY_LIGHT, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        inp_title = ctk.CTkLabel(left, text="Project Inputs",
                                  font=ctk.CTkFont(size=16, weight="bold"),
                                  text_color=C.BRAND_WHITE)
        inp_title.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self.input_frame = ScrollableInputFrame(left, fg_color=C.BRAND_NAVY_LIGHT,
                                                 scrollbar_button_color=C.BRAND_TEAL_DARK)
        self.input_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.input_frame.build()

        # ── Button bar ──
        btn_bar = ctk.CTkFrame(left, fg_color=C.BRAND_NAVY_LIGHT, height=55)
        btn_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=8)

        self.calc_btn = ctk.CTkButton(btn_bar, text="⚡  Calculate", height=40,
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       fg_color=C.BRAND_TEAL, hover_color=C.BRAND_TEAL_DARK,
                                       text_color=C.BRAND_NAVY,
                                       command=self._on_calculate)
        self.calc_btn.pack(side="left", padx=(5, 10))

        self.pdf_btn = ctk.CTkButton(btn_bar, text="Export PDF", height=40,
                                      font=ctk.CTkFont(size=13),
                                      fg_color=C.BRAND_NAVY_MID,
                                      hover_color=C.BRAND_TEAL_DARK,
                                      border_width=1, border_color=C.BRAND_TEAL,
                                      command=self._on_export_pdf, state="disabled")
        self.pdf_btn.pack(side="left", padx=5)

        self.excel_btn = ctk.CTkButton(btn_bar, text="Export Excel", height=40,
                                        font=ctk.CTkFont(size=13),
                                        fg_color=C.BRAND_NAVY_MID,
                                        hover_color=C.BRAND_TEAL_DARK,
                                        border_width=1, border_color=C.BRAND_TEAL,
                                        command=self._on_export_excel, state="disabled")
        self.excel_btn.pack(side="left", padx=5)

        # ── Right panel: Results ──
        right = ctk.CTkFrame(content, fg_color=C.BRAND_NAVY, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        res_title = ctk.CTkLabel(right, text="Results",
                                  font=ctk.CTkFont(size=16, weight="bold"),
                                  text_color=C.BRAND_WHITE)
        res_title.grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self.results_frame = ResultsFrame(right, fg_color=C.BRAND_NAVY,
                                           scrollbar_button_color=C.BRAND_TEAL_DARK)
        self.results_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # ── Status bar ──
        self.status_bar = ctk.CTkLabel(self, text="Ready", height=24,
                                        font=ctk.CTkFont(size=11),
                                        text_color=C.BRAND_GREY,
                                        fg_color=C.BRAND_NAVY_LIGHT,
                                        anchor="w")
        self.status_bar.pack(fill="x", side="bottom", padx=0)

        # Placeholder text in results
        placeholder = ctk.CTkLabel(self.results_frame,
                                    text="Enter project details and click Calculate\n"
                                         "to run the pricing model.",
                                    font=ctk.CTkFont(size=14),
                                    text_color=C.BRAND_GREY,
                                    justify="center")
        placeholder.pack(expand=True, pady=80)
        self.results_frame._widgets.append(placeholder)

    # ── Calculation ──

    def _on_calculate(self):
        self.calc_btn.configure(state="disabled", text="Calculating...")
        self.status_bar.configure(text="Running solver...", text_color=C.BRAND_AMBER_WARNING)
        self.update_idletasks()

        # Run in thread to keep UI responsive
        thread = threading.Thread(target=self._run_model, daemon=True)
        thread.start()

    def _run_model(self):
        try:
            inputs = self.input_frame.collect_inputs()
            model = PricingModel(inputs)
            result = model.solve()
            self._result = result
            self._inputs = inputs
            self.after(0, self._display_results)
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _display_results(self):
        self.results_frame.display(self._result, self._inputs)
        self.calc_btn.configure(state="normal", text="⚡  Calculate")
        self.pdf_btn.configure(state="normal")
        self.excel_btn.configure(state="normal")
        self.status_bar.configure(
            text=f"Calculation complete  —  Levered IRR: {self._result.levered_irr * 100:.2f}%  |  "
                 f"PPA: {self._result.ppa_rate_year1_pence:.2f} p/kWh  |  "
                 f"Dev Fee: £{self._result.dev_fee_total_solved:,.0f}",
            text_color=C.BRAND_GREEN
        )

    def _show_error(self, msg: str):
        self.calc_btn.configure(state="normal", text="⚡  Calculate")
        self.status_bar.configure(text=f"Error: {msg}", text_color=C.BRAND_RED_WARNING)

        self.results_frame.clear()
        err_lbl = ctk.CTkLabel(self.results_frame,
                                text=f"Calculation Error\n\n{msg}",
                                font=ctk.CTkFont(size=14),
                                text_color=C.BRAND_RED_WARNING,
                                justify="center", wraplength=500)
        err_lbl.pack(expand=True, pady=80)
        self.results_frame._widgets.append(err_lbl)

    # ── Export ──

    def _on_export_pdf(self):
        if self._result is None:
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{self._inputs.project_name.replace(' ', '_')}_Pricing_Report.pdf"
        )
        if path:
            from .reports import generate_pdf
            try:
                generate_pdf(path, self._result, self._inputs)
                self.status_bar.configure(text=f"PDF exported: {path}",
                                           text_color=C.BRAND_GREEN)
            except Exception as e:
                self.status_bar.configure(text=f"PDF export failed: {e}",
                                           text_color=C.BRAND_RED_WARNING)

    def _on_export_excel(self):
        if self._result is None:
            return
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=f"{self._inputs.project_name.replace(' ', '_')}_Pricing_Model.xlsx"
        )
        if path:
            from .reports import generate_excel
            try:
                generate_excel(path, self._result, self._inputs)
                self.status_bar.configure(text=f"Excel exported: {path}",
                                           text_color=C.BRAND_GREEN)
            except Exception as e:
                self.status_bar.configure(text=f"Excel export failed: {e}",
                                           text_color=C.BRAND_RED_WARNING)


def run_app():
    app = PricingApp()
    app.mainloop()
