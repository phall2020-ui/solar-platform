"""
Create visual plots comparing PVGIS vs SolarGIS irradiance data.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12

BASE_DIR = Path(r"c:\Users\PeterHall\OneDrive - AMPYR IDEA UK Ltd\Python scripts\Irradiation Data")

# Load batch comparison results
results_df = pd.read_csv(BASE_DIR / 'batch_comparison_results.csv')

# Create output directory for plots
plots_dir = BASE_DIR / 'plots'
plots_dir.mkdir(exist_ok=True)

print("Creating comparison plots...")

# =============================================================================
# 1. Scatter Plot: PVGIS vs SolarGIS Mean GTI
# =============================================================================
fig, ax = plt.subplots(figsize=(10, 10))

# Color by month
scatter = ax.scatter(
    results_df['SolarGIS_Mean_GTI_Wm2'],
    results_df['PVGIS_Mean_GTI_Wm2'],
    c=results_df['Month'],
    cmap='viridis',
    s=100,
    alpha=0.7,
    edgecolors='black',
    linewidth=0.5
)

# Add 1:1 line
max_val = max(results_df['SolarGIS_Mean_GTI_Wm2'].max(), results_df['PVGIS_Mean_GTI_Wm2'].max())
ax.plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='1:1 Line')

# Add regression line
z = np.polyfit(results_df['SolarGIS_Mean_GTI_Wm2'], results_df['PVGIS_Mean_GTI_Wm2'], 1)
p = np.poly1d(z)
x_line = np.linspace(0, max_val, 100)
ax.plot(x_line, p(x_line), 'b-', linewidth=2, alpha=0.7,
        label=f'Best Fit (y={z[0]:.2f}x + {z[1]:.1f})')

# Colorbar
cbar = plt.colorbar(scatter, ax=ax)
cbar.set_label('Month')
cbar.set_ticks(range(1, 12))
cbar.set_ticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])

ax.set_xlabel('SolarGIS Mean GTI (W/m²)')
ax.set_ylabel('PVGIS Mean GTI (W/m²)')
ax.set_title('PVGIS vs SolarGIS: Mean GTI Comparison\n(55 site-month combinations)')
ax.legend(loc='upper left')
ax.set_xlim(0, max_val * 1.05)
ax.set_ylim(0, max_val * 1.05)

# Add R² annotation
correlation = results_df['PVGIS_Mean_GTI_Wm2'].corr(results_df['SolarGIS_Mean_GTI_Wm2'])
ax.annotate(f'R² = {correlation**2:.3f}', xy=(0.95, 0.05), xycoords='axes fraction',
            ha='right', fontsize=12, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
plt.savefig(plots_dir / '1_scatter_pvgis_vs_solargis.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 1_scatter_pvgis_vs_solargis.png")


# =============================================================================
# 2. Monthly Comparison Bar Chart
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

monthly_means = results_df.groupby('Month').agg({
    'PVGIS_Mean_GTI_Wm2': 'mean',
    'SolarGIS_Mean_GTI_Wm2': 'mean'
}).reset_index()

months = monthly_means['Month']
x = np.arange(len(months))
width = 0.35

bars1 = ax.bar(x - width/2, monthly_means['PVGIS_Mean_GTI_Wm2'], width,
               label='PVGIS', color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.bar(x + width/2, monthly_means['SolarGIS_Mean_GTI_Wm2'], width,
               label='SolarGIS', color='#3498db', edgecolor='black', linewidth=0.5)

ax.set_xlabel('Month')
ax.set_ylabel('Mean GTI (W/m²)')
ax.set_title('Monthly Average GTI Comparison: PVGIS vs SolarGIS')
ax.set_xticks(x)
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()

# Add value labels on bars
for bar in bars1:
    height = bar.get_height()
    ax.annotate(f'{height:.0f}',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), textcoords="offset points",
                ha='center', va='bottom', fontsize=9)

for bar in bars2:
    height = bar.get_height()
    ax.annotate(f'{height:.0f}',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), textcoords="offset points",
                ha='center', va='bottom', fontsize=9)

ax.set_ylim(0, monthly_means['SolarGIS_Mean_GTI_Wm2'].max() * 1.15)

plt.tight_layout()
plt.savefig(plots_dir / '2_monthly_comparison_bars.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 2_monthly_comparison_bars.png")


# =============================================================================
# 3. Percentage Difference by Month (Box Plot)
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

# Calculate percentage difference for each row
results_df['Pct_Diff'] = ((results_df['PVGIS_Mean_GTI_Wm2'] - results_df['SolarGIS_Mean_GTI_Wm2'])
                          / results_df['SolarGIS_Mean_GTI_Wm2'] * 100)

# Create box plot
month_data = [results_df[results_df['Month'] == m]['Pct_Diff'].values for m in range(1, 12)]
bp = ax.boxplot(month_data, patch_artist=True)

# Color boxes
colors = plt.cm.viridis(np.linspace(0, 1, 11))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax.axhline(y=0, color='red', linestyle='--', linewidth=2, label='No difference')

ax.set_xlabel('Month')
ax.set_ylabel('Percentage Difference ((PVGIS - SolarGIS) / SolarGIS × 100)')
ax.set_title('Distribution of PVGIS vs SolarGIS Difference by Month')
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()

plt.tight_layout()
plt.savefig(plots_dir / '3_difference_boxplot_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 3_difference_boxplot_by_month.png")


# =============================================================================
# 4. Correlation by Month
# =============================================================================
fig, ax = plt.subplots(figsize=(12, 6))

monthly_corr = results_df.groupby('Month')['Correlation'].mean()

bars = ax.bar(range(1, 12), monthly_corr.values, color='#9b59b6',
              edgecolor='black', linewidth=0.5, alpha=0.8)

# Color bars by correlation strength
for bar, corr in zip(bars, monthly_corr.values):
    if corr >= 0.6:
        bar.set_color('#27ae60')  # Green - good
    elif corr >= 0.4:
        bar.set_color('#f39c12')  # Orange - moderate
    else:
        bar.set_color('#e74c3c')  # Red - poor

ax.axhline(y=0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Moderate threshold (0.5)')
ax.axhline(y=0.7, color='green', linestyle='--', linewidth=1, alpha=0.7, label='Good threshold (0.7)')

ax.set_xlabel('Month')
ax.set_ylabel('Mean Hourly Correlation')
ax.set_title('PVGIS vs SolarGIS Hourly Correlation by Month')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.set_ylim(0, 1)
ax.legend()

# Add value labels
for i, v in enumerate(monthly_corr.values):
    ax.text(i + 1, v + 0.02, f'{v:.2f}', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig(plots_dir / '4_correlation_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 4_correlation_by_month.png")


# =============================================================================
# 5. RMSE by Month
# =============================================================================
fig, ax = plt.subplots(figsize=(12, 6))

monthly_rmse = results_df.groupby('Month')['RMSE_Wm2'].mean()

ax.bar(range(1, 12), monthly_rmse.values, color='#e74c3c',
       edgecolor='black', linewidth=0.5, alpha=0.8)

ax.set_xlabel('Month')
ax.set_ylabel('Mean RMSE (W/m²)')
ax.set_title('PVGIS vs SolarGIS: Mean RMSE by Month')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])

# Add value labels
for i, v in enumerate(monthly_rmse.values):
    ax.text(i + 1, v + 2, f'{v:.0f}', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig(plots_dir / '5_rmse_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 5_rmse_by_month.png")


# =============================================================================
# 6. Site Comparison - Top 10 Sites by Number of Arrays
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

# Get average values per site
site_summary = results_df.groupby('Site').agg({
    'PVGIS_Mean_GTI_Wm2': 'mean',
    'SolarGIS_Mean_GTI_Wm2': 'mean',
    'Num_Arrays': 'first',
    'Total_Capacity_kWp': 'first'
}).reset_index()

# Sort by total capacity
site_summary = site_summary.sort_values('Total_Capacity_kWp', ascending=True).tail(15)

y = np.arange(len(site_summary))
height = 0.35

bars1 = ax.barh(y - height/2, site_summary['PVGIS_Mean_GTI_Wm2'], height,
                label='PVGIS', color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.barh(y + height/2, site_summary['SolarGIS_Mean_GTI_Wm2'], height,
                label='SolarGIS', color='#3498db', edgecolor='black', linewidth=0.5)

ax.set_xlabel('Mean GTI (W/m²)')
ax.set_ylabel('Site')
ax.set_title('PVGIS vs SolarGIS by Site (Top 15 by Capacity)')
ax.set_yticks(y)
ax.set_yticklabels([f"{s}\n({c:.0f} kWp)" for s, c in
                   zip(site_summary['Site'], site_summary['Total_Capacity_kWp'])])
ax.legend(loc='lower right')

plt.tight_layout()
plt.savefig(plots_dir / '6_site_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 6_site_comparison.png")


# =============================================================================
# 7. Seasonal Pattern - Monthly Energy Totals
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

monthly_totals = results_df.groupby('Month').agg({
    'PVGIS_Total_kWhm2': 'mean',
    'SolarGIS_Total_kWhm2': 'mean'
}).reset_index()

ax.fill_between(monthly_totals['Month'], 0, monthly_totals['SolarGIS_Total_kWhm2'],
                alpha=0.3, color='#3498db', label='SolarGIS')
ax.fill_between(monthly_totals['Month'], 0, monthly_totals['PVGIS_Total_kWhm2'],
                alpha=0.3, color='#2ecc71', label='PVGIS')

ax.plot(monthly_totals['Month'], monthly_totals['SolarGIS_Total_kWhm2'],
        'o-', color='#3498db', linewidth=2, markersize=8)
ax.plot(monthly_totals['Month'], monthly_totals['PVGIS_Total_kWhm2'],
        'o-', color='#2ecc71', linewidth=2, markersize=8)

ax.set_xlabel('Month')
ax.set_ylabel('Monthly Total Irradiance (kWh/m²)')
ax.set_title('Seasonal Pattern: Monthly Total Irradiance')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()
ax.set_xlim(0.5, 11.5)

plt.tight_layout()
plt.savefig(plots_dir / '7_seasonal_pattern.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 7_seasonal_pattern.png")


# =============================================================================
# 8. Summary Dashboard (4 subplots)
# =============================================================================
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# Subplot 1: Scatter
ax1 = axes[0, 0]
scatter = ax1.scatter(
    results_df['SolarGIS_Mean_GTI_Wm2'],
    results_df['PVGIS_Mean_GTI_Wm2'],
    c=results_df['Month'],
    cmap='viridis',
    s=60,
    alpha=0.7
)
max_val = max(results_df['SolarGIS_Mean_GTI_Wm2'].max(), results_df['PVGIS_Mean_GTI_Wm2'].max())
ax1.plot([0, max_val], [0, max_val], 'r--', linewidth=1.5)
ax1.set_xlabel('SolarGIS (W/m²)')
ax1.set_ylabel('PVGIS (W/m²)')
ax1.set_title('PVGIS vs SolarGIS Scatter')
plt.colorbar(scatter, ax=ax1, label='Month')

# Subplot 2: Monthly bars
ax2 = axes[0, 1]
x = np.arange(11)
width = 0.35
ax2.bar(x - width/2, monthly_means['PVGIS_Mean_GTI_Wm2'], width, label='PVGIS', color='#2ecc71')
ax2.bar(x + width/2, monthly_means['SolarGIS_Mean_GTI_Wm2'], width, label='SolarGIS', color='#3498db')
ax2.set_xlabel('Month')
ax2.set_ylabel('Mean GTI (W/m²)')
ax2.set_title('Monthly Comparison')
ax2.set_xticks(x)
ax2.set_xticklabels(['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N'])
ax2.legend()

# Subplot 3: Correlation
ax3 = axes[1, 0]
bars = ax3.bar(range(11), monthly_corr.values, color='#9b59b6', alpha=0.8)
for bar, corr in zip(bars, monthly_corr.values):
    if corr >= 0.6:
        bar.set_color('#27ae60')
    elif corr >= 0.4:
        bar.set_color('#f39c12')
    else:
        bar.set_color('#e74c3c')
ax3.axhline(y=0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7)
ax3.set_xlabel('Month')
ax3.set_ylabel('Correlation')
ax3.set_title('Hourly Correlation by Month')
ax3.set_xticks(range(11))
ax3.set_xticklabels(['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N'])
ax3.set_ylim(0, 1)

# Subplot 4: Percentage difference distribution
ax4 = axes[1, 1]
ax4.hist(results_df['Pct_Diff'], bins=20, color='#e74c3c', alpha=0.7, edgecolor='black')
ax4.axvline(x=0, color='green', linestyle='--', linewidth=2, label='No difference')
ax4.axvline(x=results_df['Pct_Diff'].mean(), color='blue', linestyle='-', linewidth=2,
            label=f'Mean: {results_df["Pct_Diff"].mean():.1f}%')
ax4.set_xlabel('Percentage Difference (%)')
ax4.set_ylabel('Frequency')
ax4.set_title('Distribution of PVGIS vs SolarGIS Difference')
ax4.legend()

plt.suptitle('PVGIS vs SolarGIS Comparison Summary\n(55 site-month combinations, Jan-Nov 2025)',
             fontsize=16, fontweight='bold', y=1.02)

plt.tight_layout()
plt.savefig(plots_dir / '8_summary_dashboard.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 8_summary_dashboard.png")


# =============================================================================
# Print completion message
# =============================================================================
print(f"\nAll plots saved to: {plots_dir}")
print("\nPlot files created:")
for f in sorted(plots_dir.glob('*.png')):
    print(f"  - {f.name}")
