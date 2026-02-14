"""Smoke test for Phase 2 — verifies runtime behavior."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 1. unified_config loads cleanly
import unified_config
print("OK  unified_config")

# 2. Page registry
from services.page_registry import find_page, get_visible_pages, PAGE_GROUPS
pages = get_visible_pages("admin")
print(f"OK  page_registry — {len(pages)} pages visible to admin")
for label, group in PAGE_GROUPS.items():
    print(f"     Group: {label} ({len(group.pages)} pages)")

dash = find_page("Dashboard")
assert dash is not None, "Dashboard not found"
detail = find_page("Plant Detail")
assert detail is not None, "Plant Detail not found"
print("OK  find_page (Dashboard, Plant Detail)")

# 3. Portfolio service
from services.portfolio_service import PortfolioService
print("OK  PortfolioService")

# 4. Plant service
from services.plant_service import PlantService
print("OK  PlantService")

# 5. Design tokens
from styles.design_tokens import AMPYR_TEAL, STATUS_COLORS, CHART_COLORS
print(f"OK  design_tokens — AMPYR_TEAL={AMPYR_TEAL}, {len(STATUS_COLORS)} statuses, {len(CHART_COLORS)} chart colors")

# 6. KPI cards
from components.kpi_cards import render_kpi_row, render_status_badge
print("OK  kpi_cards")

# 7. Breadcrumbs
from components.breadcrumbs import render_breadcrumbs
print("OK  breadcrumbs")

# 8. Layouts
from components.layouts import page_header, two_column_layout, card_grid, filter_bar
print("OK  layouts")

# 9. Portfolio map
from modules.portfolio_map import render
print("OK  portfolio_map")

# 10. Plant detail
from modules.plant_detail import render as render_detail
print("OK  plant_detail")

# 11. Dashboard
from modules.dashboard import render as render_dash
print("OK  dashboard")

print()
print("ALL SMOKE TESTS PASSED")
