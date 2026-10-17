# -*- coding: utf-8 -*-
"""扫码登录头条号（纯API，300秒窗口）：
获取二维码 -> 保存PNG供用户扫码 -> 轮询登录 -> 保存 toutiao_cookies.json"""
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
img_bytes = base64.b64decode(qr_b64)
with open(QR_IMAGE_FILE, "wb") as f:
    f.write(img_bytes)
print(f"二维码已保存: {QR_IMAGE_FILE}", flush=True)
print("请打开二维码图片，用抖音APP扫码并在手机上确认登录", flush=True)

print(f"[2] 等待扫码登录（{MAX_WAIT}秒超时）...", flush=True)
start = time.time()
last_status = ""
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

    if status == "1" and status != last_status:
        print(f"  [{elapsed}s] 已扫码，请在手机上点击确认登录", flush=True)
        last_status = status
    elif status == "2" or redirect_url:
        print(f"  [{elapsed}s] 登录成功！", flush=True)
        if redirect_url:
            session.get(redirect_url, allow_redirects=True, timeout=15)
        session.get("https://mp.toutiao.com/profile_v4/", allow_redirects=True, timeout=15)
        cookies = dict(session.cookies)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"Cookie已保存: {COOKIE_FILE}", flush=True)
        print(f"共 {len(cookies)} 个Cookie: {list(cookies.keys())}", flush=True)
        print("LOGIN_OK", flush=True)
        sys.exit(0)
    elif status == "3":
        print(f"  [{elapsed}s] 二维码已过期", flush=True)
        sys.exit(2)

print(f"\n[{MAX_WAIT}s] 超时，未检测到登录", flush=True)
sys.exit(1)
