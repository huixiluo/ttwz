# -*- coding: utf-8 -*-
"""获取二维码 -> 生成HTML展示 -> 轮询登录 -> 保存Cookie"""
import os
import sys
import time
import json
import base64
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
QR_IMAGE_FILE = os.path.join(BASE_DIR, "toutiao_qr.png")
QR_HTML_FILE = os.path.join(BASE_DIR, "output", "toutiao_qr.html")

session = requests.Session()
session.headers.update({"User-Agent": UA})

# 1. 获取二维码
print("[1] 获取登录二维码...")
resp = session.get("https://sso.toutiao.com/get_qrcode/",
                   params={"service": "https://mp.toutiao.com"}, timeout=15)
data = resp.json()
if data.get("error_code") != 0:
    print(f"错误: {data}")
    sys.exit(1)

token = data["data"]["token"]
qr_b64 = data["data"]["qrcode"]

# 保存二维码图片
img_bytes = base64.b64decode(qr_b64)
with open(QR_IMAGE_FILE, "wb") as f:
    f.write(img_bytes)

# 生成HTML展示页面
os.makedirs(os.path.dirname(QR_HTML_FILE), exist_ok=True)
html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>扫码登录头条号</title>
<style>
body {{ font-family: 'Microsoft YaHei', sans-serif; text-align: center; padding: 40px; background: #f5f5f5; }}
.container {{ background: #fff; border-radius: 12px; padding: 30px; max-width: 400px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
h2 {{ color: #333; margin-bottom: 20px; }}
img {{ border: 2px solid #eee; border-radius: 8px; }}
p {{ color: #666; margin-top: 20px; font-size: 14px; }}
</style>
</head>
<body>
<div class="container">
<h2>请用抖音APP扫码登录头条号</h2>
<img src="data:image/png;base64,{qr_b64}" width="280" height="280" alt="二维码">
<p>打开抖音APP → 点击右上角"扫一扫"<br>扫码后请在手机上点击"确认登录"</p>
</div>
</body>
</html>"""
with open(QR_HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"二维码已保存: {QR_IMAGE_FILE}")
print(f"HTML页面: {QR_HTML_FILE}")
print(f"Token: {token}")
print("\n[2] 等待扫码登录（120秒超时）...")
sys.stdout.flush()

# 2. 轮询登录状态
max_wait = 120
start = time.time()

while time.time() - start < max_wait:
    time.sleep(2)
    resp = session.get("https://sso.toutiao.com/check_qrconnect/",
                       params={"token": token, "service": "https://mp.toutiao.com",
                               "need_callback": "1"}, timeout=15)
    data = resp.json()
    inner = data.get("data", {})
    status = str(inner.get("status", "")) if isinstance(inner, dict) else ""
    redirect_url = inner.get("redirect_url", "") if isinstance(inner, dict) else ""
    elapsed = int(time.time() - start)

    if status == "1":
        print(f"  [{elapsed}s] 已扫码，请在手机上确认登录")
    elif status == "2" or redirect_url:
        print(f"  [{elapsed}s] 登录成功！")
        # 完成登录
        if redirect_url:
            session.get(redirect_url, allow_redirects=True, timeout=15)
        session.get("https://mp.toutiao.com/profile_v4/", allow_redirects=True, timeout=15)
        # 保存Cookie
        cookies = dict(session.cookies)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"\nCookie已保存: {COOKIE_FILE}")
        print(f"共 {len(cookies)} 个Cookie: {list(cookies.keys())}")
        print("登录完成！")
        sys.exit(0)
    elif status == "3":
        print(f"  [{elapsed}s] 二维码已过期，请重新运行")
        sys.exit(1)
    else:
        print(f"  [{elapsed}s] 等待扫码...")

print("\n超时，未检测到登录。")
sys.exit(1)