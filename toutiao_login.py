# -*- coding: utf-8 -*-
"""
头条号二维码登录脚本
流程：获取二维码 → 展示给用户扫码 → 轮询登录状态 → 成功后保存Cookie
"""
import os
import time
import json
import base64
import webbrowser
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
QR_IMAGE_FILE = os.path.join(BASE_DIR, "toutiao_qr.png")
QR_PAGE_FILE = os.path.join(BASE_DIR, "qr_login_page.html")

# 关键认证 Cookie 字段（任一存在即视为已登录）
AUTH_COOKIE_KEYS = ["sessionid", "login_uid", "sid_tt", "uid_tt", "sso_uid"]


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

    # 生成可预览的二维码HTML页面（内嵌base64）
    html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>头条号登录二维码</title>'
        '<style>body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;'
        'display:flex;flex-direction:column;align-items:center;justify-content:center;'
        'min-height:100vh;margin:0;background:#f5f5f5;}'
        '.card{background:#fff;padding:30px 40px;border-radius:16px;'
        'box-shadow:0 4px 24px rgba(0,0,0,0.08);text-align:center;}'
        'h2{color:#1a1a1a;margin:0 0 8px;font-size:22px;}'
        '.tip{color:#666;font-size:14px;margin-bottom:20px;}'
        'img{width:280px;height:280px;display:block;margin:0 auto;}'
        '.warn{color:#f56c6c;font-size:13px;margin-top:16px;}</style></head>'
        '<body><div class="card">'
        '<h2>头条号登录</h2>'
        '<div class="tip">请使用 <b>今日头条 APP</b> 或 <b>抖音 APP</b> 扫描下方二维码</div>'
        f'<img src="data:image/png;base64,{qr_b64}" />'
        '<div class="warn">扫码后在手机上点击「确认登录」</div>'
        '</div></body></html>'
    )
    with open(QR_PAGE_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"二维码已保存: {QR_IMAGE_FILE}")
    print(f"预览页面已生成: {QR_PAGE_FILE}")
    print(f"Token: {token}")
    return token


def check_login_status(session, token):
    """轮询登录状态
    返回: (status, extra)
        0 - 等待扫码
        1 - 已扫码待确认
        2 - 登录成功（extra=redirect_url）
        3 - 过期/需重新获取
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

    redirect_url = ""
    if isinstance(inner, dict):
        redirect_url = (inner.get("redirect_url") or inner.get("callback_url")
                        or inner.get("url") or "")

    # 首次轮询打印完整返回，便于确认状态码含义
    if not hasattr(check_login_status, "_first_printed"):
        print(f"    [debug首次返回] {data}")
        check_login_status._first_printed = True

    # 状态码映射（基于实测）：
    # status=1: 等待扫码（二维码有效）
    # status=2: 已扫码待确认
    # status=3: 已确认登录（带redirect_url）
    # status=5: 二维码过期（返回新二维码）
    if status == "3" or (status == "2" and redirect_url):
        print(f"    [debug] 登录成功，完整返回: {data}")
        return 2, redirect_url  # 登录成功
    elif status == "2":
        return 1, ""  # 已扫码待确认
    elif status == "1":
        return 0, ""  # 等待扫码
    elif status == "5":
        return 3, ""  # 过期
    elif error_code == 0 and not status:
        return 0, ""  # 等待扫码
    elif error_code == 3:
        return 3, ""  # 过期
    else:
        return -1, str(data)


def _has_auth_cookie(session):
    """检查 session 中是否已包含关键认证 Cookie"""
    for name in AUTH_COOKIE_KEYS:
        if session.cookies.get(name):
            return True
    return False


def complete_login(session, redirect_url, token):
    """完成登录跳转，获取认证Cookie
    优先用 redirect_url；为空时用 token 调用 sso 的 auth 接口兑换票据。
    """
    sso_headers = {"Referer": "https://sso.toutiao.com/"}

    if redirect_url:
        print(f"  使用 redirect_url 跳转: {redirect_url[:80]}...")
        resp = session.get(redirect_url, allow_redirects=True, timeout=15,
                           headers=sso_headers)
        print(f"  跳转完成，最终URL: {resp.url}")
    else:
        # redirect_url 为空时，主动调用 sso 的 auth 端点兑换登录票据
        print("  redirect_url 为空，尝试用 token 兑换登录票据...")
        # 方式1：auth/login_success
        auth_url = "https://sso.toutiao.com/auth/login_success/"
        resp = session.get(auth_url, params={
            "token": token,
            "service": "https://mp.toutiao.com",
        }, allow_redirects=True, timeout=15, headers=sso_headers)
        print(f"  auth/login_success 状态码: {resp.status_code}, URL: {resp.url}")

        # 方式2：get_token
        if not _has_auth_cookie(session):
            print("  未获取到认证Cookie，尝试 get_token 端点...")
            resp = session.get("https://sso.toutiao.com/get_token/", params={
                "token": token,
                "service": "https://mp.toutiao.com",
            }, allow_redirects=True, timeout=15, headers=sso_headers)
            print(f"  get_token 状态码: {resp.status_code}, URL: {resp.url}")

    # 访问 mp.toutiao.com 拿到完整 cookie
    print("  访问 mp.toutiao.com/profile_v4/ 获取完整Cookie...")
    resp2 = session.get("https://mp.toutiao.com/profile_v4/",
                        allow_redirects=True, timeout=15,
                        headers={"Referer": "https://mp.toutiao.com/"})
    print(f"  访问完成，状态码: {resp2.status_code}")

    cookie_names = [c.name for c in session.cookies]
    print(f"  当前 Cookie 字段: {cookie_names}")
    return resp2.url


def save_cookies(session):
    """保存 Cookie 到文件"""
    cookies = dict(session.cookies)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"\nCookie 已保存: {COOKIE_FILE}")
    print(f"共 {len(cookies)} 个 Cookie")

    # 关键 Cookie 检查
    has_auth = _has_auth_cookie(session)
    if has_auth:
        print("[OK] 已获取到认证Cookie，登录有效。")
    else:
        print("[警告] 未检测到关键认证Cookie（sessionid/login_uid等），登录可能失败。")
    return has_auth


def is_logged_in():
    """读取本地Cookie文件，判断是否已登录"""
    if not os.path.exists(COOKIE_FILE):
        return False
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    return any(name in cookies for name in AUTH_COOKIE_KEYS)


def load_session():
    """从本地Cookie文件加载已登录的session"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".toutiao.com")
    return session


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    print("=" * 50)
    print("头条号二维码登录")
    print("=" * 50)

    print("\n[1] 获取登录二维码...")
    token = get_qrcode(session)

    # 自动用浏览器打开二维码页面
    print("\n[2] 正在打开浏览器显示二维码...")
    webbrowser.open(f"file:///{QR_PAGE_FILE.replace(os.sep, '/')}")
    print(f"    二维码图片: {QR_IMAGE_FILE}")
    print("    请尽快用 今日头条APP 或 抖音APP 扫码，并在手机上确认登录")

    print("\n[3] 等待扫码登录...")
    max_wait = 180
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
            complete_login(session, redirect_url, token)
            ok = save_cookies(session)
            if ok:
                print("\n登录完成！Cookie已保存，可以上传文章了。")
            else:
                print("\n登录可能未完成，请重新运行脚本扫码。")
            return ok
        elif status == 3:
            print(f"  [{elapsed}s] 二维码已过期，重新获取...")
            token = get_qrcode(session)
            webbrowser.open(f"file:///{QR_PAGE_FILE.replace(os.sep, '/')}")
            start = time.time()
            continue
        else:
            print(f"  [{elapsed}s] 未知状态: {extra}")

    print("\n超时，未检测到登录。")
    return False


if __name__ == "__main__":
    main()
