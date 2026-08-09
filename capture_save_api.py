# -*- coding: utf-8 -*-
"""捕获保存API的完整请求，分析7050错误原因"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

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
co.set_address("127.0.0.1:9228")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_capture"))

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

# 检查登录
login_ok = page.run_js("""
    var url = window.location.href;
    var body = document.body ? document.body.innerText : '';
    if (url.indexOf('login') >= 0 || url.indexOf('passport') >= 0) return 'NOT_LOGIN';
    if (body.indexOf('扫码登录') >= 0 || body.indexOf('账号密码登录') >= 0) return 'NOT_LOGIN';
    return 'LOGIN_OK';
""")
print(f"  登录状态: {login_ok}")
if login_ok != 'LOGIN_OK':
    print("  [FAIL] cookies失效")
    page.quit()
    exit(1)

# 打开发布页
print("\n[2] 打开发布页...")
page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
time.sleep(6)

# 等待编辑器
for i in range(20):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        print("  [OK] 编辑器已就绪")
        break
    time.sleep(1)

# 注入更详细的网络拦截器（捕获完整请求头+body+响应）
page.run_js("""
window._capturedRequests = [];
window._capturedResponses = [];

var origFetch = window.fetch;
window.fetch = function(url, options) {
    options = options || {};
    var urlStr = typeof url === 'string' ? url : (url && url.url) || '';
    var method = (options.method || (url && url.method) || 'GET').toUpperCase();
    var body = options.body;

    if (method === 'POST' && urlStr.indexOf('publish') >= 0) {
        var bodyStr = '';
        if (typeof body === 'string') {
            bodyStr = body;
        }
        var headers = {};
        if (options.headers) {
            if (options.headers instanceof Headers) {
                for (var entry of options.headers.entries()) {
                    headers[entry[0]] = entry[1];
                }
            } else {
                headers = Object.assign({}, options.headers);
            }
        }
        window._capturedRequests.push({
            url: urlStr,
            method: method,
            body: bodyStr,
            bodyLength: bodyStr.length,
            headers: headers,
            timestamp: Date.now()
        });
    }

    var p = origFetch.apply(this, arguments);
    if (method === 'POST' && urlStr.indexOf('publish') >= 0) {
        p.then(function(resp) {
            var sc = resp.status;
            resp.clone().text().then(function(t) {
                window._capturedResponses.push({
                    url: urlStr,
                    status: sc,
                    body: t,
                    timestamp: Date.now()
                });
            }).catch(function(){});
        }).catch(function(){});
    }
    return p;
};

var origXHRSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(body) {
    if (this._method === 'POST' && (this._url||'').indexOf('publish') >= 0) {
        var bodyStr = typeof body === 'string' ? body : '[non-string]';
        window._capturedRequests.push({
            url: this._url,
            method: this._method,
            body: bodyStr,
            bodyLength: bodyStr.length,
            headers: {},
            timestamp: Date.now()
        });
    }
    var xhr = this;
    this.addEventListener('load', function() {
        if ((xhr._url||'').indexOf('publish') >= 0) {
            window._capturedResponses.push({
                url: xhr._url,
                status: xhr.status,
                body: xhr.responseText || '',
                timestamp: Date.now()
            });
        }
    });
    return origXHRSend.apply(this, arguments);
};

var origXHROpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    this._method = (method || 'GET').toUpperCase();
    return origXHROpen.apply(this, arguments);
};
""")

print("  网络拦截器已注入")

# 设置标题
title = "测试标题请忽略"
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

# 设置简单内容
page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.focus();
    // 通过ProseMirror API设置内容
    var pmView = editor.pmViewDesc;
    if (pmView && pmView.view) {
        var view = pmView.view;
        var state = view.state;
        var doc = state.schema.nodeFromJSON({
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": "这是一段测试内容，用于分析保存API的请求格式。"}]
            }]
        });
        view.dispatch(view.state.tr.replaceWith(0, state.doc.content.size, doc.content));
    }
}
""")
time.sleep(2)

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

print("\n[3] 等待保存API调用...")
time.sleep(15)

# 获取捕获的请求和响应
captured = page.run_js("""
return JSON.stringify({
    requests: window._capturedRequests || [],
    responses: window._capturedResponses || []
});
""")

try:
    data = json.loads(captured)
    requests = data.get("requests", [])
    responses = data.get("responses", [])

    print(f"\n[4] 捕获到 {len(requests)} 个保存请求:")
    for i, req in enumerate(requests):
        print(f"\n  请求 {i+1}:")
        print(f"    URL: {req.get('url','')[:150]}")
        print(f"    Method: {req.get('method','')}")
        print(f"    Body长度: {req.get('bodyLength',0)}")
        print(f"    Headers: {json.dumps(req.get('headers',{}), ensure_ascii=False)[:500]}")
        body = req.get('body','')
        if body:
            # 尝试解析body为JSON
            try:
                body_json = json.loads(body)
                print(f"    Body (JSON keys): {list(body_json.keys())}")
                # 打印关键字段
                for key in ['title', 'content', 'pgc_id', 'aid', 'type', 'source']:
                    if key in body_json:
                        val = body_json[key]
                        if isinstance(val, str) and len(val) > 200:
                            print(f"    {key}: {val[:200]}...")
                        else:
                            print(f"    {key}: {val}")
            except:
                print(f"    Body (前500字): {body[:500]}")

    print(f"\n[5] 捕获到 {len(responses)} 个保存响应:")
    for i, resp in enumerate(responses):
        print(f"\n  响应 {i+1}:")
        print(f"    URL: {resp.get('url','')[:150]}")
        print(f"    HTTP状态: {resp.get('status','')}")
        body = resp.get('body','')
        print(f"    响应体: {body[:500]}")
except Exception as e:
    print(f"解析错误: {e}")
    print(f"原始数据: {captured[:2000]}")

page.quit()
print("\nDONE")
