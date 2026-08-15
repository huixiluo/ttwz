# -*- coding: utf-8 -*-
"""requests直传图片到/spice/image"""
import json, requests, io
from PIL import Image

with open("/workspace/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

headers = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Accept": "application/json, text/plain, */*",
}

img = Image.new("RGB", (400, 240), (90, 60, 180))
buf = io.BytesIO()
img.save(buf, format="JPEG")

url = "https://mp.toutiao.com/spice/image?upload_source=20020002&need_enhance=true&aid=1231&device_platform=web"

for field in ["file", "image", "upload_file"]:
    try:
        resp = requests.post(
            url,
            files={field: ("test.jpg", buf.getvalue(), "image/jpeg")},
            headers=headers,
            timeout=30,
        )
        r = resp.text[:200]
        print(f"field={field}: {resp.status_code} {r}")
        if resp.status_code == 200 and '"code":0' in resp.text.replace(" ", ""):
            print(f"--> 成功! 字段名: {field}")
            break
    except Exception as e:
        print(f"field={field}: ERR {e}")
