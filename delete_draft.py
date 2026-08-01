# -*- coding: utf-8 -*-
"""删除旧草稿，然后尝试创建新草稿"""
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

# 访问草稿箱
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(8)

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
    var logEntry = {url: xhr._url || '', method: xhr._method || 'GET'};
    if (body) {
        if (typeof body === 'string') logEntry.reqBody = body.substring(0, 2000);
        else if (body instanceof FormData) {
            var parts = [];
            body.forEach(function(v, k) { parts.push(k + '=' + (typeof v === 'string' ? v.substring(0, 100) : '[binary]')); });
            logEntry.reqBody = 'FormData: ' + parts.join('&').substring(0, 2000);
        }
    }
    window.__apiLogs.push(logEntry);
    xhr.addEventListener('load', function() {
        logEntry.status = xhr.status;
        logEntry.response = (xhr.responseText || '').substring(0, 500);
    });
    return origXHRSend.apply(this, arguments);
};
""")

# 找到第一个"删除"按钮并点击
print("[1] 查找删除按钮...")
result = page.run_js("""
var btns = document.querySelectorAll('button, span, div');
var found = [];
for (var i = 0; i < btns.length; i++) {
    var text = (btns[i].textContent || '').trim();
    if (text === '删除' && btns[i].getBoundingClientRect().width > 0) {
        found.push({index: i, tag: btns[i].tagName, class: btns[i].className});
    }
}
return JSON.stringify(found.slice(0, 5));
""")
print(f"  找到的删除按钮: {result}")

# 尝试点击第一个删除按钮
delete_clicked = page.run_js("""
var btns = document.querySelectorAll('button, span, div');
for (var i = 0; i < btns.length; i++) {
    var text = (btns[i].textContent || '').trim();
    if (text === '删除' && btns[i].getBoundingClientRect().width > 0) {
        btns[i].scrollIntoView({block: 'center'});
        var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
        btns[i].dispatchEvent(evt);
        return 'clicked at index ' + i;
    }
}
return 'not_found';
""")
print(f"  删除按钮点击: {delete_clicked}")

time.sleep(2)

# 检查是否有确认弹窗
confirm_result = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('确定') !== -1 && body.indexOf('删除') !== -1) return 'confirm_dialog';
return 'no_dialog: ' + body.substring(0, 200);
""")
print(f"  确认弹窗: {confirm_result}")

# 如果有确认弹窗，点击确定
if 'confirm_dialog' in str(confirm_result):
    confirm_clicked = page.run_js("""
var btns = document.querySelectorAll('button, span, div');
for (var i = 0; i < btns.length; i++) {
    var text = (btns[i].textContent || '').trim();
    if (text === '确定' && btns[i].getBoundingClientRect().width > 0) {
        var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
        btns[i].dispatchEvent(evt);
        return 'confirmed';
    }
}
return 'not_found';
""")
    print(f"  确认删除: {confirm_clicked}")
    time.sleep(3)

# 检查删除API
print("\n[2] 删除API日志:")
api_logs = page.run_js("""
var apiLogs = window.__apiLogs || [];
var results = [];
for (var j = 0; j < apiLogs.length; j++) {
    var log = apiLogs[j];
    if (log.url.indexOf('delete') !== -1 || log.url.indexOf('remove') !== -1 || log.url.indexOf('del') !== -1) {
        results.push(log.method + ' ' + log.url.substring(0, 100) + ' status=' + (log.status || 'pending') + ' resp=' + (log.response || 'none'));
    }
}
return results.join('\\n') || 'no delete API calls';
""")
print(api_logs)

# 检查草稿数量
count = page.run_js("""
var body = document.body.innerText;
var match = body.match(/共\\s*(\\d+)\\s*条/);
return match ? match[1] : 'unknown';
""")
print(f"\n[3] 当前草稿数: {count}")

page.quit()