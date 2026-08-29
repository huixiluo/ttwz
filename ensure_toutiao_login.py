# -*- coding: utf-8 -*-
"""确保头条创作者平台已登录：
1. 若 toutiao_cookies.json 存在且有效 → 直接返回成功
2. 否则/失效 → 弹出浏览器到登录页，用户手动登录后自动保存 cookies
"""
import os, json, time, sys
from DrissionPage import ChromiumPage, ChromiumOptions

BASE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE, "toutiao_cookies.json")
MP_URL = "https://mp.toutiao.com"
LOGIN_WAIT_MAX = 180  # 用户最多180秒登录时间

BROWSER_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def _cookies_to_dict(cookie_list):
    """DrissionPage list[{name,value,...}] -> dict{name:value}"""
    out = {}
    for c in cookie_list:
        if isinstance(c, dict) and "name" in c and "value" in c:
            out[c["name"]] = c["value"]
    return out


def _check_login(page):
    """检测是否已登录。返回 True/False."""
    try:
        # 多信号判定：
        # - 页面出现"登录/注册"文案 → 未登录
        # - 页面出现账号头像/昵称/创作者中心 → 已登录
        # - 页面跳转包含passport/sso → 未登录
        url = page.url or ""
        if "passport" in url or "sso" in url or "login" in url.lower():
            return False
        text = page.run_js("return document.body.innerText.substring(0,3000);") or ""
        if "登录" in text and ("注册" in text or "手机号" in text or "扫码" in text or "密码" in text):
            # 需要排除"退出登录"这种情况
            if "退出登录" in text or "切换账号" in text:
                return True
            return False
        if "创作者" in text or ("草稿" in text and "管理" in text) or "数据" in text:
            return True
        # 尝试找头像/昵称元素
        has_user = page.run_js("""
var el = document.querySelector('img[src*="avatar"], .user-info, .profile-avatar, [class*="avatar"]');
if (el) return 'yes';
var txt = document.body.innerText;
if (txt.indexOf('您好') !== -1 || txt.indexOf('欢迎回来') !== -1) return 'yes';
return null;
""")
        if has_user == "yes":
            return True
        # 兜底：url 在 mp.toutiao.com 且没有登录文案
        if "mp.toutiao.com" in url and ("创作" in text or "数据" in text or "内容管理" in text):
            return True
        return None  # 不确定
    except Exception as e:
        print(f"  [WARN] 登录检测异常: {e}")
        return None


def ensure_login():
    co = ChromiumOptions()
    if os.path.exists(BROWSER_PATH):
        co.set_browser_path(BROWSER_PATH)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    page = ChromiumPage(co)

    # 第一步：尝试加载旧 cookies
    had_cookies = False
    if os.path.exists(COOKIE_FILE):
        try:
            cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
            page.get(MP_URL)
            time.sleep(2)
            if isinstance(cookies, dict):
                for n, v in cookies.items():
                    try:
                        page.set.cookies({"name": n, "value": str(v), "domain": ".toutiao.com", "path": "/"})
                    except Exception:
                        pass
            page.get(MP_URL)
            time.sleep(4)
            had_cookies = True
        except Exception as e:
            print(f"  [WARN] 加载旧cookies失败: {e}")
    else:
        page.get(MP_URL)
        time.sleep(4)

    # 第二步：检测登录态
    status = _check_login(page)
    if status is True:
        # 已登录 → 刷新保存当前 cookies
        cur = _cookies_to_dict(page.cookies(as_dict=False) if hasattr(page.cookies, '__call__') else page.cookies())
        # 兼容 DrissionPage 两种 API
        try:
            raw = page.cookies(all_domains=True)
        except Exception:
            raw = page.cookies
        if isinstance(raw, list):
            cur = _cookies_to_dict(raw)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        print("[OK] 已登录（使用现有cookies），已刷新保存到 toutiao_cookies.json")
        page.quit()
        return True

    # 未登录 → 需要用户手动登录
    print("=" * 60)
    if had_cookies:
        print("[!] 现有cookies已失效，需要重新登录")
    else:
        print("[!] 未检测到登录cookies，请在浏览器中完成登录")
    print("请在已打开的浏览器页面中完成头条创作者平台登录（手机号/微信/抖音扫码均可）")
    print(f"登录完成后系统将自动检测，最长等待 {LOGIN_WAIT_MAX} 秒")
    print("=" * 60)

    # 如果当前还在passport页就保留，否则跳转到登录入口
    try:
        cur_url = page.url
        if "passport" not in cur_url and "login" not in cur_url.lower():
            page.get(MP_URL)
            time.sleep(2)
    except Exception:
        pass

    start = time.time()
    while time.time() - start < LOGIN_WAIT_MAX:
        remaining = int(LOGIN_WAIT_MAX - (time.time() - start))
        status = _check_login(page)
        if status is True:
            # 登录成功 → 保存 cookies
            time.sleep(3)
            try:
                raw = page.cookies(all_domains=True)
            except Exception:
                raw = page.cookies
            cur = _cookies_to_dict(raw) if isinstance(raw, list) else raw
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] 登录成功！已保存 {len(cur)} 条 cookies 到 toutiao_cookies.json")
            time.sleep(1)
            page.quit()
            return True
        # 每10秒显示一次倒计时
        elapsed = int(time.time() - start)
        if elapsed % 10 == 0:
            sys.stdout.write(f"\r  等待登录中... 剩余 {remaining} 秒")
            sys.stdout.flush()
        time.sleep(1)

    print(f"\n[FAIL] 等待超时（{LOGIN_WAIT_MAX}秒），未检测到登录成功")
    page.quit()
    return False


if __name__ == "__main__":
    ok = ensure_login()
    sys.exit(0 if ok else 1)
