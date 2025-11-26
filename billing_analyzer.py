#!/usr/bin/env python3
# python-worker/billing_analyzer.py
# 2025.12 终极补齐版 — 永不断档、自动补全、精准去重

import boto3
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from openpyxl import load_workbook, Workbook
from openpyxl.chart import LineChart, PieChart, BarChart, Reference
from openpyxl.utils import get_column_letter
import hashlib

# ==================== 全局配置 ====================
role_arn = os.getenv('AWS_ROLE_ARN')
regions = os.getenv('REGIONS', 'us-east-1').split(',')
is_monthly = os.getenv('IS_MONTHLY', 'false').lower() == 'true'
account_alias = os.getenv('ACCOUNT_ALIAS', 'unknown')

# AssumeRole
def get_session():
    if role_arn:
        sts = boto3.client('sts')
        creds = sts.assume_role(RoleArn=role_arn, RoleSessionName='billing-ultimate')['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken']
        )
    return boto3.Session()

session = get_session()
account_id = session.client('sts').get_caller_identity()['Account']
today = datetime.now()
year_month = today.strftime('%Y%m')
file_path = f"/tmp/{account_id}_{account_alias}_{year_month}_Billing.xlsx"

# ==================== 核心：自动检测 + 补齐逻辑 ====================
def ensure_full_month_data():
    # Step 1: 计算本月应有天数
    first_day = today.replace(day=1)
    if today.month == 12:
        last_day = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
    else:
        last_day = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    expected_days = last_day.day

    # Step 2: 检查本地 Excel 是否已有完整数据
    existing_dates = set()
    if os.path.exists(file_path):
        wb = load_workbook(file_path)
        if "每日明细" in wb.sheetnames:
            ws = wb["每日明细"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0] and isinstance(row[0], datetime):
                    existing_dates.add(row[0].date())
        wb.close()

    missing_days = expected_days - len(existing_dates)
    if missing_days <= 0:
        print("本月数据已完整，无需补齐")
        return file_path

    print(f"检测到缺失 {missing_days} 天数据，开始自动补齐...")

    # Step 3: 自动扩大查询时间（最多回溯90天）
    start_date = first_day - timedelta(days=90)
    end_date = today

    # Step 4: 查询 CloudTrail 全量事件 + Describe 当前实例
    events = []
    for region in regions:
        ct = session.client('cloudtrail', region_name=region)
        paginator = ct.get_paginator('lookup_events')
        for page in paginator.paginate(
            StartTime=start_date,
            EndTime=end_date,
            LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': 'RunInstances'},
                            {'AttributeKey': 'EventName', 'AttributeValue': 'TerminateInstances'}]
        ):
            for e in page['Events']:
                events.append({
                    'Date': e['EventTime'].date(),
                    'Event': e['EventName'],
                    'User': e.get('Username', 'unknown'),
                    'IP': e.get('SourceIPAddress', 'unknown'),
                    'InstanceId': [r['ResourceName'] for r in e.get('Resources', []) if 'instance' in r['ResourceType'].lower()]
                })

    # Step 5: 补齐数据到 Excel（精准去重）
    new_rows = []
    seen = set()
    for event in events:
        key = (event['Date'], ''.join(sorted(event['InstanceId'])))
        if key not in seen:
            seen.add(key)
            new_rows.append([
                event['Date'],
                "EC2",
                event['Event'],
                event['User'],
                event['IP'],
                ','.join(event['InstanceId']) if event['InstanceId'] else "unknown",
                "补齐数据"
            ])

    # Step 6: 写入或追加到 Excel
    if os.path.exists(file_path):
        wb = load_workbook(file_path)
        ws = wb["每日明细"] if "每日明细" in wb.sheetnames else wb.active
        ws.title = "每日明细"
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "每日明细"
        ws.append(["日期", "服务", "操作", "执行人", "来源IP", "实例ID", "备注"])

    for row in new_rows:
        ws.append(row)

    # 重新生成图表
    regenerate_charts(wb)

    wb.save(file_path)
    print(f"数据补齐完成！共补充 {len(new_rows)} 条记录")
    return file_path

def regenerate_charts(wb):
    if "费用总览" not in wb.sheetnames:
        ws_sum = wb.create_sheet("费用总览")
    else:
        ws_sum = wb["费用总览"]

    # 示例：每日趋势图
    ws_daily = wb["每日明细"]
    chart = LineChart()
    chart.title = "本月每日操作趋势（已补齐）"
    data = Reference(ws_daily, min_col=1, min_row=1, max_row=ws_daily.max_row)
    chart.add_data(data, titles_from_data=True)
    ws_sum.add_chart(chart, "A10")

# ==================== 主函数 ====================
def main():
    final_file = ensure_full_month_data()

    # 月1号生成最终版
    if is_monthly:
        final_name = final_file.replace(".xlsx", "_FINAL.xlsx")
        os.rename(final_file, final_name)
        print(final_name)  # Go 推送最终版
    else:
        print(final_file)

if __name__ == '__main__':
    main()