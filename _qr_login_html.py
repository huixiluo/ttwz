# -*- coding: utf-8 -*-
"""扫码登录头条号 v2：二维码嵌入HTML页面（浏览器可直接打开）+ 300秒轮询"""
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
QR_HTML_FILE = os.path.join(BASE_DIR, "output", "toutiao_qr.html")
MAX_WAIT = 300

session = requests.Session()
session.headers.update({"User-Agent": UA})

print("[1] 获取登录二维码...", flush=True)
resp = session.get("https://sso.toutiao.com/get_qrcode/",
                   params={"service": "https://mp.toutiao.com"}, timeout=15)
data = resp.json()
if data.get("error_code") != 0:
    print(f"错误: {data}", flush=True)
    sys.exit(1)

token = data["data"]["token"]
qr_b64 = data["data"]["qrcode"]

# 生成HTML展示页（二维码base64内嵌）
os.makedirs(os.path.dirname(QR_HTML_FILE), exist_ok=True)
html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>扫码登录头条号</title>
<style>
body {{ font-family: 'Microsoft YaHei', sans-serif; text-align: center; padding: 40px; background: #f5f5f5; }}
.container {{ background: #fff; border-radius: 12px; padding: 30px; max-width: 420px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
h2 {{ color: #333; margin-bottom: 20px; }}
img {{ border: 2px solid #eee; border-radius: 8px; width: 280px; height: 280px; }}
p {{ color: #666; margin-top: 20px; font-size: 14px; line-height: 1.8; }}
.step {{ text-align: left; margin-top: 15px; color: #444; font-size: 14px; }}
</style>
</head>
<body>
<div class="container">
<h2>请用抖音APP扫码登录头条号</h2>
<img src="data:image/png;base64,{qr_b64}" alt="二维码">
<div class="step">
1. 打开手机抖音APP<br>
2. 点击右上角"扫一扫"<br>
3. 扫描上方二维码<br>
4. 在手机上点击"确认登录"
</div>
<p>二维码5分钟内有效，请尽快扫码</p>
</div>
</body>
</html>"""
with open(QR_HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html)
print(f"HTML页面已生成: {QR_HTML_FILE}", flush=True)
print("请用浏览器打开该页面，扫码登录", flush=True)

print(f"[2] 等待扫码登录（{MAX_WAIT}秒超时）...", flush=True)
start = time.time()
while time.time() - start < MAX_WAIT:
    time.sleep(3)
    try:
        resp = session.get("https://sso.toutiao.com/check_qrconnect/",
                           params={"token": token, "service": "https://mp.toutiao.com",
                                   "need_callback": "1"}, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"  轮询异常: {e}", flush=True)
        continue
    inner = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    status = str(inner.get("status", ""))
    redirect_url = inner.get("redirect_url", "")
    elapsed = int(time.time() - start)

    if status == "2" or redirect_url:
        print(f"  [{elapsed}s] 登录成功！", flush=True)
        if redirect_url:
            session.get(redirect_url, allow_redirects=True, timeout=15)
        session.get("https://mp.toutiao.com/profile_v4/", allow_redirects=True, timeout=15)
        cookies = dict(session.cookies)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"Cookie已保存: {COOKIE_FILE}", flush=True)
        print(f"共 {len(cookies)} 个Cookie", flush=True)
        print("LOGIN_OK", flush=True)
        sys.exit(0)
    elif status == "3":
        print(f"  [{elapsed}s] 二维码已过期", flush=True)
        sys.exit(2)
    elif elapsed % 30 < 3:
        print(f"  [{elapsed}s] 等待扫码确认...", flush=True)

print(f"\n[{MAX_WAIT}s] 超时，未检测到登录", flush=True)
sys.exit(1)
