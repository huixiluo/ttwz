import requests, json, re

with open("/workspace/toutiao_cookies.json") as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mp.toutiao.com/",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 获取发布页面
resp = session.get("https://mp.toutiao.com/profile_v4/graphic/publish")
print(f"Page status: {resp.status_code}, length: {len(resp.text)}")

# 搜索所有JS文件
js_urls = re.findall(r'(?:src|href)="([^"]*\.js[^"]*)"', resp.text)
print(f"Found {len(js_urls)} JS files")

# 搜索关键API
for pattern in ['save_ugc_draft', 'save_draft', 'article_type', 'save.*draft', 'agw/draft', 'agw/', 'publish', '/api/']:
    matches = re.findall(r'[^.]*' + pattern + r'[^.]*', resp.text, re.IGNORECASE)
    if matches:
        print(f"\nPattern '{pattern}': {matches[:10]}")

# 搜索article_type的可能值
atype_matches = re.findall(r'article_type[^;]{0,200}', resp.text, re.IGNORECASE)
print(f"\narticle_type references: {atype_matches[:10]}")

# 搜索API端点模式
api_patterns = re.findall(r'["\'](/[^"\']*(?:api|agw|draft|publish|article)[^"\']*)["\']', resp.text, re.IGNORECASE)
print(f"\nAPI-like URLs: {api_patterns[:20]}")

# 保存HTML供分析
with open("/workspace/mp_publish_page.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("\nSaved HTML to /workspace/mp_publish_page.html for analysis")