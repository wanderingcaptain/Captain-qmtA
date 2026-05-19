import os
# # 强制要求所有网络请求不使用代理
# os.environ['no_proxy'] = '*'
# os.environ['NO_PROXY'] = '*'

import akshare as ak
import pandas as pd

# 抓取贵州茅台(600519)今年的前复权日线行情
print("正在连接接口获取数据，请稍候...")
df = ak.stock_zh_a_hist(
    symbol="600519", 
    period="daily", 
    start_date="20260101", 
    end_date="20260515", 
    adjust="qfq"
)

print("\n数据抓取成功！前5个交易日的数据如下：")
print(df.head())