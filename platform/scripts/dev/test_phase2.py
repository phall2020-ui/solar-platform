"""Quick test of Phase 2 imports."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Pre-import unified_config to simulate normal app startup order
import unified_config

errors = []
tests = [
    ("styles.design_tokens", ["AMPYR_TEAL", "STATUS_COLORS", "CHART_COLORS", "PLOTLY_TEMPLATE"]),
    ("styles", ["apply_theme", "AMPYR_TEAL"]),
    ("services.page_registry", ["PAGE_GROUPS", "find_page", "get_all_page_names"]),
    ("services.portfolio_service", ["PortfolioService", "PortfolioSummary"]),
    ("services.plant_service", ["PlantService"]),
    ("components.kpi_cards", ["render_kpi_row"]),
    ("components.breadcrumbs", ["render_breadcrumbs"]),
    ("components.layouts", ["page_header", "card_grid"]),
    ("modules.plant_detail", ["render_plant_detail"]),
    ("modules.portfolio_map", ["render_portfolio_map"]),
]

for mod_name, attrs in tests:
    try:
        m = __import__(mod_name, fromlist=attrs)
        for a in attrs:
            getattr(m, a)
        print("OK   " + mod_name)
    except Exception as e:
        errors.append(mod_name + ": " + str(e))
        print("FAIL " + mod_name + ": " + str(e))

print("")
print("Total errors: " + str(len(errors)))
if errors:
    sys.exit(1)
else:
    print("ALL IMPORTS OK")
