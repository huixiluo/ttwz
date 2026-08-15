# -*- coding: utf-8 -*-
"""测试图片上传API"""
import json, requests, base64

BASE_DIR = "/workspace"
with open(f"{BASE_DIR}/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

session = requests.Session()
for k, v in cookies_dict.items():
    session.cookies.set(k, v, domain=".toutiao.com")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# 生成1x1红色测试JPEG
from PIL import Image
import io
img = Image.new("RGB", (100, 60), (200, 50, 50))
buf = io.BytesIO()
img.save(buf, format="JPEG")
img_data = buf.getvalue()

resp = session.post(
    "https://mp.toutiao.com/mp/agw/spice/image",
    files={"file": ("test.jpg", img_data, "image/jpeg")},
    data={"source": "mp", "type": "article"},
    headers=headers,
    timeout=30,
)
print("status:", resp.status_code)
print("resp:", resp.text[:400])
