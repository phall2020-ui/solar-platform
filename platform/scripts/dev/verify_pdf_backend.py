import pandas as pd
from modules.chart_utils import create_heatmap_chart, create_shading_chart
from modules.report_generator import PDFReportGenerator
import datetime
import os

def test_headless_report():
    print("--- Testing Headless Report Generation ---")
    
    # 1. Mock Data
    dates = pd.date_range(start="2025-01-01", periods=6, freq="ME")
    sites = ["Site A", "Site B", "Site C"]
    
    data = []
    for d in dates:
        d_str = d.strftime("%b-%y")
        for s in sites:
            data.append({
                "Site": s,
                "Date": d_str,
                "Loss_Total_Tech_kWh": 100 * len(s) # Dummy logic
            })
            
    df = pd.DataFrame(data)
    print("Mock Data Created")
    
    # 2. Create Figures
    pivot = df.pivot_table(index="Site", columns="Date", values="Loss_Total_Tech_kWh")
    fig_hm = create_heatmap_chart(pivot, "Test Loss")
    print(f"Heatmap Created: {fig_hm is not None}")
    
    # 3. Generate PDF
    try:
        gen = PDFReportGenerator(title="Test Report", subtitle="Headless Generation Check")
        gen.add_section_header("Headless Heatmap")
        if fig_hm:
            gen.add_plot(fig_hm)
            
        pdf_bytes = gen.generate()
        print(f"PDF Generated. Size: {len(pdf_bytes)} bytes")
        
        # Save to artifacts for inspection
        with open("test_headless_report.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("Saved to test_headless_report.pdf")
        
    except Exception as e:
        print(f"PDF Generation Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_headless_report()
