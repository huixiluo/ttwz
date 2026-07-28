# -*- coding: utf-8 -*-
"""
头条号二维码登录脚本
流程：获取二维码 → 展示给用户扫码 → 轮询登录状态 → 成功后保存Cookie
"""
import os
import time
import json
import base64
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
QR_IMAGE_FILE = os.path.join(BASE_DIR, "toutiao_qr.png")


def get_qrcode(session):
    """获取登录二维码，返回 token"""
    url = "https://sso.toutiao.com/get_qrcode/"
    params = {"service": "https://mp.toutiao.com"}
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error_code") != 0:
        raise RuntimeError(f"获取二维码失败: {data}")

    token = data["data"]["token"]
    qr_b64 = data["data"]["qrcode"]

    img_bytes = base64.b64decode(qr_b64)
    with open(QR_IMAGE_FILE, "wb") as f:
        f.write(img_bytes)

    print(f"二维码已保存: {QR_IMAGE_FILE}")
    print(f"Token: {token}")
    return token


def check_login_status(session, token):
    """轮询登录状态
    返回: (status, extra)
        0 - 等待扫码
        1 - 已扫码待确认
        2 - 登录成功（extra=redirect_url）
        3 - 过期
    """
    url = "https://sso.toutiao.com/check_qrconnect/"
    params = {
        "token": token,
        "service": "https://mp.toutiao.com",
        "need_callback": "1",
    }
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    error_code = data.get("error_code", -1)
    inner = data.get("data", {})
    status = str(inner.get("status", "")) if isinstance(inner, dict) else ""

    # 真正的状态在 data.status 里
    # status=1: 已扫码待确认
    # status=2: 已确认，登录成功，此时有 redirect_url
    # 无 status 且 error_code=0 且无 redirect_url: 也算待确认
    redirect_url = ""
    if isinstance(inner, dict):
        redirect_url = inner.get("redirect_url") or inner.get("callback_url") or inner.get("url") or ""

    if status == "1":
        return 1, ""  # 已扫码待确认
    elif status == "2" or redirect_url:
        print(f"    [debug] 登录成功，完整返回: {data}")
        return 2, redirect_url  # 登录成功
    elif error_code == 0 and not status:
        return 0, ""  # 等待扫码
    elif error_code == 3:
        return 3, ""  # 过期
    else:
        return -1, str(data)


def complete_login(session, redirect_url):
    """用 redirect_url 完成登录，redirect_url为空时直接访问mp.toutiao.com"""
    if redirect_url:
        resp = session.get(redirect_url, allow_redirects=True, timeout=15)
        print(f"登录跳转完成，最终URL: {resp.url}")
    else:
        print("redirect_url为空，直接访问mp.toutiao.com获取Cookie...")
    # 访问 mp.toutiao.com 确保拿到完整cookie
    resp2 = session.get("https://mp.toutiao.com/profile_v4/", allow_redirects=True, timeout=15)
    print(f"访问mp.toutiao.com完成，状态码: {resp2.status_code}")
    return resp2.url


def save_cookies(session):
    """保存 Cookie 到文件"""
    cookies = dict(session.cookies)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"\nCookie 已保存: {COOKIE_FILE}")
    print(f"共 {len(cookies)} 个 Cookie")


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    print("=" * 50)
    print("头条号二维码登录")
    print("=" * 50)

    print("\n[1] 获取登录二维码...")
    token = get_qrcode(session)

    print("\n[2] 请用抖音APP扫描二维码")
    print(f"    二维码图片: {QR_IMAGE_FILE}")
    print("    请在120秒内完成扫码并确认登录")

    print("\n[3] 等待扫码登录...")
    max_wait = 120
    start = time.time()

    while time.time() - start < max_wait:
        time.sleep(2)
        status, extra = check_login_status(session, token)
        elapsed = int(time.time() - start)

        if status == 0:
            print(f"  [{elapsed}s] 等待扫码...")
        elif status == 1:
            print(f"  [{elapsed}s] 已扫码，请在手机上确认登录")
        elif status == 2:
            print(f"  [{elapsed}s] 登录成功！")
            redirect_url = extra
            print("\n[4] 完成登录跳转...")
            complete_login(session, redirect_url)
            save_cookies(session)
            print("\n登录完成！Cookie已保存。")
            return True
        elif status == 3:
            print(f"  [{elapsed}s] 二维码已过期，请重新运行")
            return False
        else:
            print(f"  [{elapsed}s] 未知状态: {extra}")

    print("\n超时，未检测到登录。")
    return False


if __name__ == "__main__":
    main()
