# -*- coding: utf-8 -*-
"""捕获保存API的完整请求body"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions
from urllib.parse import unquote, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

print("[1] 启动浏览器...")
co = ChromiumOptions()
co.set_browser_path(CHROME_PATH)
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--window-size=1920,1080")
co.set_argument("--disable-background-timer-throttling")
co.set_argument("--disable-backgrounding-occluded-windows")
co.set_argument("--disable-renderer-backgrounding")
co.set_address("127.0.0.1:9229")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_full"))

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass

page.get("https://mp.toutiao.com")
time.sleep(3)

# 打开发布页
page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
time.sleep(6)

for i in range(20):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        print("  [OK] 编辑器已就绪")
        break
    time.sleep(1)

# 注入拦截器 - 捕获完整body
page.run_js("""
window._fullBody = '';
window._fullHeaders = {};

var origFetch = window.fetch;
window.fetch = function(url, options) {
    options = options || {};
    var urlStr = typeof url === 'string' ? url : (url && url.url) || '';
    var method = (options.method || 'GET').toUpperCase();

    if (method === 'POST' && urlStr.indexOf('publish') >= 0) {
        var body = options.body;
        if (typeof body === 'string') {
            window._fullBody = body;
        }
        // 捕获headers
        if (options.headers) {
            if (options.headers instanceof Headers) {
                var h = {};
                for (var entry of options.headers.entries()) {
                    h[entry[0]] = entry[1];
                }
                window._fullHeaders = h;
            } else {
                window._fullHeaders = Object.assign({}, options.headers);
            }
        }
    }

    return origFetch.apply(this, arguments);
};

var origXHRSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(body) {
    if (this._method === 'POST' && (this._url||'').indexOf('publish') >= 0) {
        if (typeof body === 'string') {
            window._fullBody = body;
        }
        // 捕获XHR headers
        try {
            window._fullHeaders = {
                'Content-Type': this.getRequestHeader('Content-Type') || '',
                'X-CSRFToken': this.getRequestHeader('X-CSRFToken') || ''
            };
        } catch(e) {}
    }
    return origXHRSend.apply(this, arguments);
};

var origXHROpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    this._method = (method || 'GET').toUpperCase();
    return origXHROpen.apply(this, arguments);
};
""")

# 设置标题
title = "测试标题请忽略2"
page.run_js(f"""
var el = document.querySelector('textarea[placeholder*="文章标题"]') ||
         document.querySelector('textarea[placeholder*="请输入文章标题"]');
if (el) {{
    el.focus();
    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(el, {json.dumps(title)});
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
    el.blur();
}}
""")
print(f"  标题已设置: {title}")
time.sleep(3)

# 模拟按键触发保存
page.run_js("var e=document.querySelector('.ProseMirror'); if(e){e.focus();}")
time.sleep(0.5)
page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space',
              windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space',
              windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
time.sleep(0.3)
page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key='Backspace', code='Backspace',
              windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key='Backspace', code='Backspace',
              windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)

print("\n[2] 等待保存API调用...")
time.sleep(15)

# 获取完整body
full_body = page.run_js("return window._fullBody;") or ""
full_headers = page.run_js("return JSON.stringify(window._fullHeaders);") or "{}"

print(f"\n[3] 完整请求body ({len(full_body)}字符):")

# 解析URL-encoded body
if full_body:
    parsed = parse_qs(full_body, keep_blank_values=True)
    print(f"\n  字段列表:")
    for key in parsed:
        values = parsed[key]
        if values:
            val = values[0]
            if len(val) > 200:
                print(f"    {key}: {val[:200]}... (总长{len(val)})")
            else:
                print(f"    {key}: {val}")

    # 保存完整body到文件
    with open(os.path.join(BASE_DIR, "save_request_body.txt"), "w", encoding="utf-8") as f:
        f.write(full_body)
    print(f"\n  完整body已保存到 save_request_body.txt")

    # 也保存解析后的JSON
    parsed_json = {}
    for key in parsed:
        parsed_json[key] = parsed[key][0] if parsed[key] else ""
    with open(os.path.join(BASE_DIR, "save_request_parsed.json"), "w", encoding="utf-8") as f:
        json.dump(parsed_json, f, ensure_ascii=False, indent=2)
    print(f"  解析后的字段已保存到 save_request_parsed.json")

print(f"\n[4] Headers: {full_headers}")

page.quit()
print("\nDONE")
