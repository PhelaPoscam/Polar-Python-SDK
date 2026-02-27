#!/usr/bin/env python3
"""
Check EDA data in exported file
"""
import pandas as pd

# Read app export
app_export = pd.read_csv('data/Exported Data/Nuanic 2026-02-27T08_48_38.217Z.csv')

print('=== EDA COLUMN ANALYSIS ===\n')
print(f'Total rows: {len(app_export)}')
print(f'EDA column nulls: {app_export["eda"].isna().sum()}')
print(f'EDA column non-nulls: {(~app_export["eda"].isna()).sum()}')
print(f'Percentage with EDA data: {(~app_export["eda"].isna()).sum() / len(app_export) * 100:.1f}%')

print('\n=== FIRST 20 ROWS WITH EDA DATA ===')
eda_data = app_export[~app_export['eda'].isna()]
if len(eda_data) > 0:
    print(eda_data[['time', 'dne', 'eda']].head(20).to_string())
else:
    print('No EDA data found')

print(f'\n=== EDA DATA STATISTICS ===')
if len(eda_data) > 0:
    print(f'Min EDA: {app_export["eda"].min():.6f}')
    print(f'Max EDA: {app_export["eda"].max():.6f}')
    print(f'Mean EDA: {app_export["eda"].mean():.6f}')
    print(f'First 10 EDA values:')
    for i, val in enumerate(eda_data['eda'].head(10)):
        print(f'  {i+1}. {val}')
