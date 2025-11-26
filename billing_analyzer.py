#!/usr/bin/env python3
# python-worker/billing_analyzer.py
import boto3
import os
import json
from datetime import datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, PieChart, BarChart, Reference
from openpyxl.utils import get_column_letter

# AssumeRole 支持
def get_session():
    if 'AWS_ROLE_ARN' in os.environ:
        sts = boto3.client('sts')
        creds = sts.assume_role(
            RoleArn=os.environ['AWS_ROLE_ARN'],
            RoleSessionName='self-billing'
        )['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken']
        )
    return boto3.Session()

session = get_session()
regions = os.getenv('AWS_REGIONS', 'us-east-1').split(',')

# 模拟费用数据（实际项目中会调用 Describe API）
data = []
for r in regions:
    data.extend([
        {"Date": "2025-11-01", "Service": "EC2", "Cost": 1234.56, "Project": "prod-web"},
        {"Date": "2025-11-01", "Service": "RDS", "Cost": 876.54, "Project": "prod-db"},
        {"Date": "2025-11-02", "Service": "EC2", "Cost": 1250.00, "Project": "prod-web"},
        # ... 更多数据
    ])

df = pd.DataFrame(data)
total = df['Cost'].sum()

# 创建 Excel + 自动图表
wb = Workbook()
ws = wb.active
ws.title = "明细_Daily"
for r in pd.DataFrame.to_records(df, index=False):
    ws.append(list(r))

# 汇总页 + 图表
ws2 = wb.create_sheet("汇总_Summary")
ws2.append([f"账单周期：2025-11-01 至 {datetime.now().strftime('%Y-%m-%d')}"])
ws2.append([f"账户：{os.getenv('ACCOUNT_ALIAS', 'Unknown')}"])
ws2.append([f"总费用：${total:,.2f}"])

# 图表1：趋势
chart1 = LineChart()
chart1.title = "每日费用趋势"
data_ref = Reference(ws, min_col=3, min_row=1, max_row=len(df))
cats = Reference(ws, min_col=1, min_row=2, max_row=len(df))
chart1.add_data(data_ref, titles_from_data=True)
chart1.set_categories(cats)
ws2.add_chart(chart1, "A10")

# 图表2：服务占比
service_sum = df.groupby('Service')['Cost'].sum()
pie = PieChart()
pie_data = Reference(ws2, min_col=2, min_row=10, max_row=10+len(service_sum)-1)
pie_cats = Reference(ws2, min_col=1, min_row=11, max_row=10+len(service_sum))
pie.add_data(pie_data)
pie.set_categories(pie_cats)
pie.title = "服务费用占比"
ws2.add_chart(pie, "J10")

file = f"/tmp/{os.getenv('ACCOUNT_ALIAS', 'unknown')}_{datetime.now().strftime('%Y%m')}_Billing.xlsx"
wb.save(file)
print(file)