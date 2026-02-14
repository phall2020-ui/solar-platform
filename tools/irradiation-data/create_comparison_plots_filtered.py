"""
Create visual plots comparing PVGIS vs SolarGIS irradiance data.
Removes outliers and develops correction factor methodology.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
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

# Calculate percentage difference consistently
results_df['Pct_Diff'] = ((results_df['PVGIS_Mean_GTI_Wm2'] - results_df['SolarGIS_Mean_GTI_Wm2'])
                          / results_df['SolarGIS_Mean_GTI_Wm2'] * 100)

# Create output directory for plots
plots_dir = BASE_DIR / 'plots'
plots_dir.mkdir(exist_ok=True)

print("="*80)
print("OUTLIER REMOVAL AND CORRECTION FACTOR ANALYSIS")
print("="*80)

# =============================================================================
# Outlier Removal using multiple criteria
# =============================================================================
print("\n--- Outlier Identification ---")
print(f"Original data points: {len(results_df)}")

# Criterion 1: Remove points with very low correlation (< 0.3)
# These indicate poor model fit for that site/month
low_corr_mask = results_df['Correlation'] < 0.3
print(f"Low correlation (< 0.3): {low_corr_mask.sum()} points")

# Criterion 2: Remove extreme percentage differences (> 2 std from mean)
mean_pct = results_df['Pct_Diff'].mean()
std_pct = results_df['Pct_Diff'].std()
extreme_diff_mask = (results_df['Pct_Diff'] < mean_pct - 2*std_pct) | (results_df['Pct_Diff'] > mean_pct + 2*std_pct)
print(f"Extreme differences (>2 std): {extreme_diff_mask.sum()} points")

# Criterion 3: Remove points with very high RMSE relative to mean GTI
results_df['RMSE_Ratio'] = results_df['RMSE_Wm2'] / results_df['SolarGIS_Mean_GTI_Wm2']
high_rmse_mask = results_df['RMSE_Ratio'] > 1.0  # RMSE > 100% of mean
print(f"High RMSE ratio (>100%): {high_rmse_mask.sum()} points")

# Combined outlier mask
outlier_mask = low_corr_mask | extreme_diff_mask | high_rmse_mask
print(f"\nTotal outliers: {outlier_mask.sum()}")

# Show outliers
if outlier_mask.sum() > 0:
    print("\nOutliers removed:")
    outliers = results_df[outlier_mask][['Site', 'Month', 'Correlation', 'Pct_Diff', 'RMSE_Ratio']]
    print(outliers.to_string())

# Filtered dataset
filtered_df = results_df[~outlier_mask].copy()
print(f"\nFiltered data points: {len(filtered_df)}")

# Save filtered results
filtered_df.to_csv(BASE_DIR / 'batch_comparison_results_filtered.csv', index=False)
print(f"Saved filtered results to: batch_comparison_results_filtered.csv")

# =============================================================================
# Recalculate statistics on filtered data
# =============================================================================
print("\n" + "="*80)
print("FILTERED DATA STATISTICS")
print("="*80)

print(f"\nOverall Statistics (filtered):")
print(f"  Mean PVGIS GTI:     {filtered_df['PVGIS_Mean_GTI_Wm2'].mean():.1f} W/m²")
print(f"  Mean SolarGIS GTI:  {filtered_df['SolarGIS_Mean_GTI_Wm2'].mean():.1f} W/m²")
print(f"  Mean Difference:    {filtered_df['Pct_Diff'].mean():.1f}%")
print(f"  Std Difference:     {filtered_df['Pct_Diff'].std():.1f}%")
print(f"  Mean Correlation:   {filtered_df['Correlation'].mean():.3f}")
print(f"  Mean RMSE:          {filtered_df['RMSE_Wm2'].mean():.1f} W/m²")

# =============================================================================
# CORRECTION FACTOR METHODOLOGY
# =============================================================================
print("\n" + "="*80)
print("CORRECTION FACTOR METHODOLOGY")
print("="*80)

# Method 1: Simple linear regression (overall)
slope, intercept, r_value, p_value, std_err = stats.linregress(
    filtered_df['PVGIS_Mean_GTI_Wm2'],
    filtered_df['SolarGIS_Mean_GTI_Wm2']
)

print("\n--- Method 1: Linear Regression (Overall) ---")
print(f"  SolarGIS = {slope:.4f} × PVGIS + {intercept:.2f}")
print(f"  R² = {r_value**2:.4f}")
print(f"  To correct PVGIS: multiply by {slope:.3f} and add {intercept:.1f}")

# Method 2: Monthly correction factors
print("\n--- Method 2: Monthly Correction Factors ---")
monthly_factors = filtered_df.groupby('Month').apply(
    lambda x: pd.Series({
        'mean_ratio': x['SolarGIS_Mean_GTI_Wm2'].mean() / x['PVGIS_Mean_GTI_Wm2'].mean(),
        'slope': stats.linregress(x['PVGIS_Mean_GTI_Wm2'], x['SolarGIS_Mean_GTI_Wm2'])[0] if len(x) > 2 else np.nan,
        'intercept': stats.linregress(x['PVGIS_Mean_GTI_Wm2'], x['SolarGIS_Mean_GTI_Wm2'])[1] if len(x) > 2 else np.nan,
        'n_samples': len(x)
    })
).reset_index()

print("\nMonth | Ratio | Slope | Intercept | N")
print("-" * 45)
for _, row in monthly_factors.iterrows():
    print(f"  {int(row['Month']):2d}  | {row['mean_ratio']:.3f} | {row['slope']:.3f} | {row['intercept']:7.1f} | {int(row['n_samples'])}")

# Method 3: Seasonal correction factors
print("\n--- Method 3: Seasonal Correction Factors ---")
def get_season(month):
    if month in [12, 1, 2]:
        return 'Winter'
    elif month in [3, 4, 5]:
        return 'Spring'
    elif month in [6, 7, 8]:
        return 'Summer'
    else:
        return 'Autumn'

filtered_df['Season'] = filtered_df['Month'].apply(get_season)

seasonal_factors = filtered_df.groupby('Season').apply(
    lambda x: pd.Series({
        'mean_ratio': x['SolarGIS_Mean_GTI_Wm2'].mean() / x['PVGIS_Mean_GTI_Wm2'].mean(),
        'mean_corr': x['Correlation'].mean(),
        'n_samples': len(x)
    })
).reset_index()

print("\nSeason  | Ratio | Correlation | N")
print("-" * 40)
for _, row in seasonal_factors.iterrows():
    print(f"{row['Season']:8s} | {row['mean_ratio']:.3f} | {row['mean_corr']:.3f}       | {int(row['n_samples'])}")

# Save correction factors
correction_factors = {
    'overall': {
        'slope': slope,
        'intercept': intercept,
        'r_squared': r_value**2
    },
    'monthly': monthly_factors.to_dict('records'),
    'seasonal': seasonal_factors.to_dict('records')
}

# =============================================================================
# RECOMMENDATION
# =============================================================================
print("\n" + "="*80)
print("RECOMMENDED CORRECTION APPROACH")
print("="*80)

print("""
Based on the analysis, we recommend using a MONTHLY CORRECTION FACTOR approach:

1. For each month, apply the correction:

   Corrected_GTI = PVGIS_GTI × Monthly_Ratio

   Or for more accuracy:

   Corrected_GTI = (PVGIS_GTI × Monthly_Slope) + Monthly_Intercept

2. The correction accounts for:
   - Systematic bias in the PVGIS synthetic cloud model
   - Seasonal variations in model accuracy
   - UK-specific climate patterns not captured by clear-sky models

3. For months with insufficient data (N < 3), use the overall correction:

   Corrected_GTI = PVGIS_GTI × {:.3f} + {:.1f}

4. Quality check: If hourly correlation < 0.4, flag the data as unreliable
""".format(slope, intercept))

# =============================================================================
# REGENERATE PLOTS WITH FILTERED DATA
# =============================================================================
print("\n" + "="*80)
print("GENERATING PLOTS WITH FILTERED DATA")
print("="*80)

# Monthly means for filtered data
monthly_means = filtered_df.groupby('Month').agg({
    'PVGIS_Mean_GTI_Wm2': 'mean',
    'SolarGIS_Mean_GTI_Wm2': 'mean'
}).reset_index()

monthly_corr = filtered_df.groupby('Month')['Correlation'].mean()

# =============================================================================
# Plot 1: Scatter with filtered data and correction line
# =============================================================================
fig, ax = plt.subplots(figsize=(10, 10))

scatter = ax.scatter(
    filtered_df['SolarGIS_Mean_GTI_Wm2'],
    filtered_df['PVGIS_Mean_GTI_Wm2'],
    c=filtered_df['Month'],
    cmap='viridis',
    s=100,
    alpha=0.7,
    edgecolors='black',
    linewidth=0.5
)

max_val = max(filtered_df['SolarGIS_Mean_GTI_Wm2'].max(), filtered_df['PVGIS_Mean_GTI_Wm2'].max()) * 1.1

# 1:1 line
ax.plot([0, max_val], [0, max_val], 'r--', linewidth=2, label='1:1 Line')

# Best fit line
x_line = np.linspace(0, max_val, 100)
ax.plot(x_line, slope * x_line + intercept, 'b-', linewidth=2, alpha=0.7,
        label=f'Best Fit: y = {slope:.2f}x + {intercept:.1f}')

# Inverse correction line (what PVGIS should be multiplied by)
ax.plot(x_line, x_line / slope - intercept/slope, 'g-', linewidth=2, alpha=0.7,
        label=f'Correction: PVGIS × {slope:.2f}')

cbar = plt.colorbar(scatter, ax=ax)
cbar.set_label('Month')
cbar.set_ticks(range(1, 12))
cbar.set_ticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])

ax.set_xlabel('SolarGIS Mean GTI (W/m²)')
ax.set_ylabel('PVGIS Mean GTI (W/m²)')
ax.set_title(f'PVGIS vs SolarGIS: Mean GTI Comparison (Filtered)\n{len(filtered_df)} data points, R² = {r_value**2:.3f}')
ax.legend(loc='upper left')
ax.set_xlim(0, max_val)
ax.set_ylim(0, max_val)

plt.tight_layout()
plt.savefig(plots_dir / '1_scatter_pvgis_vs_solargis.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 1_scatter_pvgis_vs_solargis.png")

# =============================================================================
# Plot 2: Monthly Comparison Bar Chart
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

months = monthly_means['Month']
x = np.arange(len(months))
width = 0.35

bars1 = ax.bar(x - width/2, monthly_means['PVGIS_Mean_GTI_Wm2'], width,
               label='PVGIS', color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.bar(x + width/2, monthly_means['SolarGIS_Mean_GTI_Wm2'], width,
               label='SolarGIS', color='#3498db', edgecolor='black', linewidth=0.5)

ax.set_xlabel('Month')
ax.set_ylabel('Mean GTI (W/m²)')
ax.set_title('Monthly Average GTI Comparison: PVGIS vs SolarGIS (Filtered)')
ax.set_xticks(x)
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()

for bar in bars1:
    height = bar.get_height()
    ax.annotate(f'{height:.0f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)

for bar in bars2:
    height = bar.get_height()
    ax.annotate(f'{height:.0f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=9)

ax.set_ylim(0, monthly_means['SolarGIS_Mean_GTI_Wm2'].max() * 1.15)

plt.tight_layout()
plt.savefig(plots_dir / '2_monthly_comparison_bars.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 2_monthly_comparison_bars.png")

# =============================================================================
# Plot 3: Box Plot of Percentage Difference by Month
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

month_data = [filtered_df[filtered_df['Month'] == m]['Pct_Diff'].values for m in range(1, 12)]
bp = ax.boxplot(month_data, patch_artist=True)

colors = plt.cm.viridis(np.linspace(0, 1, 11))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

ax.axhline(y=0, color='red', linestyle='--', linewidth=2, label='No difference')
ax.axhline(y=filtered_df['Pct_Diff'].mean(), color='blue', linestyle='-', linewidth=2,
           label=f'Mean: {filtered_df["Pct_Diff"].mean():.1f}%')

ax.set_xlabel('Month')
ax.set_ylabel('Percentage Difference ((PVGIS - SolarGIS) / SolarGIS × 100)')
ax.set_title('Distribution of PVGIS vs SolarGIS Difference by Month (Filtered)')
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()

plt.tight_layout()
plt.savefig(plots_dir / '3_difference_boxplot_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 3_difference_boxplot_by_month.png")

# =============================================================================
# Plot 4: Correlation by Month
# =============================================================================
fig, ax = plt.subplots(figsize=(12, 6))

bars = ax.bar(range(1, 12), monthly_corr.values, color='#9b59b6',
              edgecolor='black', linewidth=0.5, alpha=0.8)

for bar, corr in zip(bars, monthly_corr.values):
    if corr >= 0.6:
        bar.set_color('#27ae60')
    elif corr >= 0.4:
        bar.set_color('#f39c12')
    else:
        bar.set_color('#e74c3c')

ax.axhline(y=0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Moderate (0.5)')
ax.axhline(y=0.7, color='green', linestyle='--', linewidth=1, alpha=0.7, label='Good (0.7)')

ax.set_xlabel('Month')
ax.set_ylabel('Mean Hourly Correlation')
ax.set_title('PVGIS vs SolarGIS Hourly Correlation by Month (Filtered)')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.set_ylim(0, 1)
ax.legend()

for i, v in enumerate(monthly_corr.values):
    ax.text(i + 1, v + 0.02, f'{v:.2f}', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig(plots_dir / '4_correlation_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 4_correlation_by_month.png")

# =============================================================================
# Plot 5: RMSE by Month
# =============================================================================
fig, ax = plt.subplots(figsize=(12, 6))

monthly_rmse = filtered_df.groupby('Month')['RMSE_Wm2'].mean()

ax.bar(range(1, 12), monthly_rmse.values, color='#e74c3c',
       edgecolor='black', linewidth=0.5, alpha=0.8)

ax.set_xlabel('Month')
ax.set_ylabel('Mean RMSE (W/m²)')
ax.set_title('PVGIS vs SolarGIS: Mean RMSE by Month (Filtered)')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])

for i, v in enumerate(monthly_rmse.values):
    ax.text(i + 1, v + 2, f'{v:.0f}', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig(plots_dir / '5_rmse_by_month.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 5_rmse_by_month.png")

# =============================================================================
# Plot 6: Site Comparison
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

site_summary = filtered_df.groupby('Site').agg({
    'PVGIS_Mean_GTI_Wm2': 'mean',
    'SolarGIS_Mean_GTI_Wm2': 'mean',
    'Num_Arrays': 'first',
    'Total_Capacity_kWp': 'first'
}).reset_index()

site_summary = site_summary.sort_values('Total_Capacity_kWp', ascending=True).tail(15)

y = np.arange(len(site_summary))
height = 0.35

bars1 = ax.barh(y - height/2, site_summary['PVGIS_Mean_GTI_Wm2'], height,
                label='PVGIS', color='#2ecc71', edgecolor='black', linewidth=0.5)
bars2 = ax.barh(y + height/2, site_summary['SolarGIS_Mean_GTI_Wm2'], height,
                label='SolarGIS', color='#3498db', edgecolor='black', linewidth=0.5)

ax.set_xlabel('Mean GTI (W/m²)')
ax.set_ylabel('Site')
ax.set_title('PVGIS vs SolarGIS by Site - Top 15 by Capacity (Filtered)')
ax.set_yticks(y)
ax.set_yticklabels([f"{s}\n({c:.0f} kWp)" for s, c in
                   zip(site_summary['Site'], site_summary['Total_Capacity_kWp'])])
ax.legend(loc='lower right')

plt.tight_layout()
plt.savefig(plots_dir / '6_site_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 6_site_comparison.png")

# =============================================================================
# Plot 7: Seasonal Pattern
# =============================================================================
fig, ax = plt.subplots(figsize=(14, 8))

monthly_totals = filtered_df.groupby('Month').agg({
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
ax.set_title('Seasonal Pattern: Monthly Total Irradiance (Filtered)')
ax.set_xticks(range(1, 12))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'])
ax.legend()
ax.set_xlim(0.5, 11.5)

plt.tight_layout()
plt.savefig(plots_dir / '7_seasonal_pattern.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 7_seasonal_pattern.png")

# =============================================================================
# Plot 8: Summary Dashboard
# =============================================================================
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# Subplot 1: Scatter with correction
ax1 = axes[0, 0]
scatter = ax1.scatter(
    filtered_df['SolarGIS_Mean_GTI_Wm2'],
    filtered_df['PVGIS_Mean_GTI_Wm2'],
    c=filtered_df['Month'],
    cmap='viridis',
    s=60,
    alpha=0.7
)
max_val = max(filtered_df['SolarGIS_Mean_GTI_Wm2'].max(), filtered_df['PVGIS_Mean_GTI_Wm2'].max())
ax1.plot([0, max_val], [0, max_val], 'r--', linewidth=1.5, label='1:1')
ax1.plot([0, max_val], [0, max_val/slope], 'g-', linewidth=1.5, label=f'Corrected (×{slope:.2f})')
ax1.set_xlabel('SolarGIS (W/m²)')
ax1.set_ylabel('PVGIS (W/m²)')
ax1.set_title(f'Scatter with Correction Line (R²={r_value**2:.3f})')
ax1.legend(loc='upper left')
plt.colorbar(scatter, ax=ax1, label='Month')

# Subplot 2: Monthly bars
ax2 = axes[0, 1]
x = np.arange(len(monthly_means))
width = 0.35
ax2.bar(x - width/2, monthly_means['PVGIS_Mean_GTI_Wm2'], width, label='PVGIS', color='#2ecc71')
ax2.bar(x + width/2, monthly_means['SolarGIS_Mean_GTI_Wm2'], width, label='SolarGIS', color='#3498db')
ax2.set_xlabel('Month')
ax2.set_ylabel('Mean GTI (W/m²)')
ax2.set_title('Monthly Comparison')
ax2.set_xticks(x)
ax2.set_xticklabels(['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N'])
ax2.legend()

# Subplot 3: Monthly correction factors
ax3 = axes[1, 0]
ratios = monthly_factors['mean_ratio'].values
bars = ax3.bar(range(1, 12), ratios, color='#9b59b6', alpha=0.8, edgecolor='black')
ax3.axhline(y=1.0, color='red', linestyle='--', linewidth=2, label='No correction needed')
ax3.axhline(y=slope, color='green', linestyle='-', linewidth=2, label=f'Overall factor ({slope:.2f})')
ax3.set_xlabel('Month')
ax3.set_ylabel('Correction Factor (SolarGIS/PVGIS)')
ax3.set_title('Monthly Correction Factors')
ax3.set_xticks(range(1, 12))
ax3.set_xticklabels(['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N'])
ax3.legend()
for i, v in enumerate(ratios):
    ax3.text(i + 1, v + 0.02, f'{v:.2f}', ha='center', fontsize=9)

# Subplot 4: Histogram of corrected differences
ax4 = axes[1, 1]
corrected_pvgis = filtered_df['PVGIS_Mean_GTI_Wm2'] * slope + intercept
corrected_diff = (corrected_pvgis - filtered_df['SolarGIS_Mean_GTI_Wm2']) / filtered_df['SolarGIS_Mean_GTI_Wm2'] * 100

ax4.hist(filtered_df['Pct_Diff'], bins=15, alpha=0.5, color='red', label=f'Original (mean={filtered_df["Pct_Diff"].mean():.1f}%)', edgecolor='black')
ax4.hist(corrected_diff, bins=15, alpha=0.5, color='green', label=f'Corrected (mean={corrected_diff.mean():.1f}%)', edgecolor='black')
ax4.axvline(x=0, color='black', linestyle='-', linewidth=2)
ax4.set_xlabel('Percentage Difference (%)')
ax4.set_ylabel('Frequency')
ax4.set_title('Effect of Correction Factor')
ax4.legend()

plt.suptitle('PVGIS vs SolarGIS: Filtered Analysis with Correction Factors\n'
             f'({len(filtered_df)} data points after outlier removal)',
             fontsize=16, fontweight='bold', y=1.02)

plt.tight_layout()
plt.savefig(plots_dir / '8_summary_dashboard.png', dpi=150, bbox_inches='tight')
plt.close()
print("  Saved: 8_summary_dashboard.png")

# =============================================================================
# Save correction factors to CSV
# =============================================================================
correction_df = pd.DataFrame({
    'Month': range(1, 12),
    'Month_Name': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov'],
    'Correction_Ratio': monthly_factors['mean_ratio'].values,
    'Regression_Slope': monthly_factors['slope'].values,
    'Regression_Intercept': monthly_factors['intercept'].values,
    'N_Samples': monthly_factors['n_samples'].values.astype(int),
    'Mean_Correlation': monthly_corr.values
})

correction_df.to_csv(BASE_DIR / 'pvgis_correction_factors.csv', index=False)
print(f"\n  Saved correction factors to: pvgis_correction_factors.csv")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"Original data points:  {len(results_df)}")
print(f"Outliers removed:      {outlier_mask.sum()}")
print(f"Filtered data points:  {len(filtered_df)}")
print(f"\nOverall correction factor: {slope:.3f}")
print(f"After correction, mean difference reduced from {filtered_df['Pct_Diff'].mean():.1f}% to {corrected_diff.mean():.1f}%")
