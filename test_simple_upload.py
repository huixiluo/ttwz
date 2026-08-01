# -*- coding: utf-8 -*-
"""测试简单上传：纯文本，看保存是否成功"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

co = ChromiumOptions()
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass

page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(4)

# 关闭弹窗
try:
    close_btn = page.ele('text:关闭', timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except Exception:
    pass

# 注入XHR拦截器
page.run_js("""
window.__apiLogs = [];
var origXHROpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    this._method = method;
    this._url = typeof url === 'string' ? url : (url.toString ? url.toString() : '');
    return origXHROpen.apply(this, arguments);
};
var origXHRSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(body) {
    var xhr = this;
    var urlStr = xhr._url || '';
    var logEntry = {url: urlStr, method: xhr._method || 'GET'};
    if (body) {
        if (typeof body === 'string') logEntry.reqBody = body.substring(0, 5000);
        else if (body instanceof FormData) {
            var parts = [];
            body.forEach(function(v, k) { parts.push(k + '=' + (typeof v === 'string' ? v.substring(0, 100) : '[binary]')); });
            logEntry.reqBody = 'FormData: ' + parts.join('&').substring(0, 5000);
        }
    }
    window.__apiLogs.push(logEntry);
    xhr.addEventListener('load', function() {
        logEntry.status = xhr.status;
        logEntry.response = (xhr.responseText || '').substring(0, 1000);
    });
    return origXHRSend.apply(this, arguments);
};
""")

# 填写标题
print("[1] 填写标题...")
title = "测试纯文本保存"
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.clear()
    title_el.input(title)
    time.sleep(0.5)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.dispatchEvent(new Event('blur', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('input', {bubbles: true})); }
""")
    print(f"  标题: {title}")

# 填写纯文本正文（无图片）
print("[2] 填写纯文本正文...")
simple_text = "<p>这是一篇测试文章，用于验证头条号草稿箱的保存功能是否正常工作。</p><p>如果这篇文章能够成功保存到草稿箱，说明保存API本身没有问题，问题可能出在图片内容上。</p><p>本文仅为测试用途。</p>"
result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'not_found';
editor.innerHTML = '';
editor.focus();
var dt = new DataTransfer();
dt.setData('text/html', {json.dumps(simple_text)});
var pasteEvent = new ClipboardEvent('paste', {{
  bubbles: true,
  cancelable: true,
  clipboardData: dt
}});
editor.dispatchEvent(pasteEvent);
return 'ok';
""")
print(f"  正文结果: {result}")

# 等待保存
print("[3] 等待保存...")
for i in range(20):
    time.sleep(2)
    status = page.run_js("""
var body = document.body.innerText;
var results = [];
if (body.indexOf('草稿已保存') !== -1) results.push('SAVED');
if (body.indexOf('已保存') !== -1) results.push('SAVED');
if (body.indexOf('保存成功') !== -1) results.push('SAVED');
if (body.indexOf('草稿保存中') !== -1) results.push('SAVING');
if (body.indexOf('保存失败') !== -1) results.push('FAIL');

var apiLogs = window.__apiLogs || [];
var publishLogs = [];
for (var j = 0; j < apiLogs.length; j++) {
    var log = apiLogs[j];
    if (log.url.indexOf('publish') !== -1) {
        publishLogs.push(log.method + ' ' + log.url.substring(0, 80) + ' status=' + (log.status || 'pending') + ' resp=' + (log.response || 'none').substring(0, 300));
    }
}
if (results.length === 0) results.push('idle');
results.push('PUBLISH_API: ' + (publishLogs.length > 0 ? publishLogs.join(' | ') : 'none'));
return results.join('\\n');
""")
    print(f"  [{i+1}] {status}")
    if 'SAVED' in status:
        print("\n[SUCCESS] 纯文本保存成功！")
        break
    if 'FAIL' in status:
        print("\n[FAIL] 纯文本也保存失败！")

# 显示完整publish请求体
print("\n[4] 完整publish请求体:")
full_body = page.run_js("""
var apiLogs = window.__apiLogs || [];
var results = [];
for (var j = 0; j < apiLogs.length; j++) {
    var log = apiLogs[j];
    if (log.url.indexOf('publish') !== -1 && log.reqBody) {
        results.push('PUBLISH BODY: ' + log.reqBody);
        results.push('PUBLISH RESP: ' + (log.response || 'none'));
    }
}
return results.join('\\n---\\n') || 'no publish logs';
""")
print(full_body[:3000])

page.quit()