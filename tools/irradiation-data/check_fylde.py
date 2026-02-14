import pandas as pd
df = pd.read_excel('ADE CRM Data Request.xlsx')
fylde = df[df['asset_name'].str.contains('Fylde', case=False, na=False)]
print(fylde[['asset_name', 'nameplate_dc_capacity_kwp']].to_string())
