# -*- coding: utf-8 -*-
"""用真实键盘输入触发autosave，捕获保存端点"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
chrome_path = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
if os.path.exists(chrome_path):
    co.set_browser_path(chrome_path)
co.auto_port()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.headless()
page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass
page.get(PUBLISH_URL)
time.sleep(8)

for text in ["不恢复", "关闭"]:
    try:
        btn = page.ele(f"text:{text}", timeout=2)
        if btn:
            btn.click(); time.sleep(1)
    except Exception:
        pass
page.run_js("""
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { mask.click(); mask.remove(); }
""")

# XHR hook（重点捕获save/draft）
page.run_js("""
window._apiResults = [];
var OrigXHR = window.XMLHttpRequest;
function HookedXHR() {
    var xhr = new OrigXHR();
    var origOpen = xhr.open;
    var origSend = xhr.send;
    var _url = '';
    xhr.open = function(m, u) {
        _url = u;
        return origOpen.apply(xhr, arguments);
    };
    xhr.send = function(body) {
        var u = String(_url);
        if (u.indexOf('save') >= 0 || u.indexOf('draft') >= 0 || u.indexOf('publish') >= 0 || u.indexOf('/mp/agw/article') >= 0) {
            var bodyStr = '';
            try {
                if (body instanceof FormData) {
                    bodyStr = 'FORMDATA: ';
                    for (var pair of body.entries()) {
                        var v = String(pair[1]);
                        bodyStr += pair[0] + '=' + (v.length > 200 ? v.substring(0, 200) + '...' : v) + ' & ';
                    }
                } else {
                    bodyStr = String(body || '').substring(0, 600);
                }
            } catch(e) { bodyStr = 'ERR'; }
            var entry = {url: u.substring(0, 200), method: 'XHR', body: bodyStr};
            window._apiResults.push(entry);
            xhr.addEventListener('load', function() {
                entry.status = xhr.status;
                entry.resp = String(xhr.responseText || '').substring(0, 500);
            });
        }
        return origSend.apply(xhr, arguments);
    };
    return xhr;
}
window.XMLHttpRequest = HookedXHR;
return 'hooked';
""")

# 标题
title_json = json.dumps("键盘输入测试-可删除")
title_js = """
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.focus();
    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(el, TITLE);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
}
""".replace("TITLE", title_json)
page.run_js(title_js)

# 真实键盘输入正文
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(0.5)
    page.actions.type('这是用来测试自动保存机制的一段文字，内容本身没有意义。')
    print("已键盘输入正文，等待60秒观察autosave...")
    time.sleep(60)
else:
    print("未找到编辑器")

print("\n=== 捕获的save/draft API请求 ===")
api_results = page.run_js("return JSON.stringify(window._apiResults, null, 1);")
print(api_results[:5000] if api_results else "无请求")

ui_text = page.run_js("""
var t = document.body.innerText;
var m = t.match(/.{0,40}(草稿|保存中|已保存).{0,40}/g);
return m ? m.slice(0, 8).join('\\n') : '无';
""")
print("\n=== UI保存提示 ===")
print(ui_text)

page.quit()
