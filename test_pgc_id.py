#!/usr/bin/env python
"""测试获取pgc_id"""
import os, json, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

with open(COOKIE_FILE) as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.toutiao.com/",
    "Origin": "https://mp.toutiao.com",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 测试 article/new
resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
    "article_type": 0,
    "format": "json",
    "compat": 1,
    "column_no": "",
})
data = resp.json()
print("article/new 完整响应:")
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])

# 在data中搜索pgc_id
def find_pgc_id(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if 'pgc' in k.lower() or 'id' in k.lower():
                print(f"  找到: {path}.{k} = {v}")
            find_pgc_id(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_pgc_id(v, f"{path}[{i}]")

print("\n搜索pgc_id:")
find_pgc_id(data)