# -*- coding: utf-8 -*-
"""调试保存：截图+网络监控，找到保存失败原因"""
import os, re, json, time, base64
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
title = art["title"][:30]
html_path = art["html_file"]
cover_files = art["cover_files"]

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
body_html = ""
if body_match:
    body = body_match.group(1)
    parts = []
    for m in re.finditer(
        r'(<p>(.*?)</p>)|'
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            parts.append('<p>' + re.sub(r'<[^>]+>', '', m.group(2)) + '</p>')
        elif m.group(4):
            parts.append('<p><img src="' + m.group(4) + '" /></p>')
    body_html = "\n".join(parts)

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
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
print("[OK] 登录")

# Inject network monitor
page.run_js("""
window.__apiLogs = [];
var origFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    var method = (options && options.method) || 'GET';
    var body = (options && options.body) ? (typeof options.body === 'string' ? options.body.substring(0, 2000) : '') : '';
    var logEntry = {url: urlStr, method: method, time: new Date().toISOString(), reqBody: body};
    window.__apiLogs.push(logEntry);
    return origFetch.apply(this, arguments).then(function(resp) {
        var clone = resp.clone();
        clone.text().then(function(t) {
            logEntry.status = resp.status;
            logEntry.response = t.substring(0, 1000);
        }).catch(function(){});
        return resp;
    });
};
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
    var method = xhr._method || 'GET';
    var logEntry = {url: urlStr, method: method, time: new Date().toISOString(), type: 'xhr'};
    if (body) {
        if (typeof body === 'string') logEntry.reqBody = body.substring(0, 2000);
        else if (body instanceof FormData) {
            var parts = [];
            body.forEach(function(v, k) { parts.push(k + '=' + (typeof v === 'string' ? v.substring(0, 200) : '[binary]')); });
            logEntry.reqBody = 'FormData: ' + parts.join('&').substring(0, 2000);
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

page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(6)
for i in range(10):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        break
    time.sleep(1)
try:
    btn = page.ele("text:关闭", timeout=2)
    if btn:
        btn.click()
        time.sleep(1)
except:
    pass

# 填标题
print(f"\n标题: {title}")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
title_el.click()
time.sleep(0.3)
title_el.input(title)
time.sleep(0.5)
page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")

# 等待标题保存
print("等待标题保存...")
for i in range(20):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'idle';
""")
    if s == 'SAVED':
        print(f"  标题已保存 ({i+1}s)")
        break
else:
    print("  标题保存未确认")

# 填正文 - 使用JS paste
print("\n填正文...")
result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'editor_not_found';
editor.focus();
editor.innerHTML = '';
var dt = new DataTransfer();
dt.setData('text/html', {json.dumps(body_html)});
editor.dispatchEvent(new ClipboardEvent('paste', {{
    bubbles: true, cancelable: true, clipboardData: dt
}}));
editor.dispatchEvent(new Event('input', {{bubbles: true}}));
editor.dispatchEvent(new Event('change', {{bubbles: true}}));
return 'ok';
""")
print(f"  paste result: {result}")
time.sleep(2)

# 检查编辑器
pm_count = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
print(f"  ProseMirror count: {pm_count}")
if pm_count > 0:
    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  正文: {chars}字, {imgs}张图片")

# 等30秒看保存
print("\n等待保存...")
for i in range(30):
    time.sleep(1)
    status = page.run_js("""
var body = document.body.innerText;
var results = [];
if (body.indexOf('草稿已保存') !== -1) results.push('草稿已保存');
if (body.indexOf('已保存') !== -1) results.push('已保存');
if (body.indexOf('保存成功') !== -1) results.push('保存成功');
if (body.indexOf('草稿保存中') !== -1) results.push('草稿保存中');
if (body.indexOf('保存失败') !== -1) results.push('保存失败');
if (body.indexOf('错误') !== -1) results.push('错误');
if (results.length === 0) results.push('idle');
return results.join(', ');
""")
    if i % 3 == 0:
        print(f"  [{i}s] {status}")

# 网络日志
print("\n网络请求:")
logs = page.run_js("""
var logs = window.__apiLogs || [];
var results = [];
for (var i = 0; i < logs.length; i++) {
    var l = logs[i];
    if (l.url.indexOf('publish') !== -1 || l.url.indexOf('save') !== -1 || l.url.indexOf('draft') !== -1) {
        results.push(l.method + ' ' + l.url.substring(0, 100) + ' status=' + (l.status || 'pending') + ' resp=' + (l.response || '').substring(0, 300));
    }
}
return results.join('\\n') || 'no relevant logs';
""")
print(logs)

# 所有fetch日志
print("\n所有fetch日志:")
all_logs = page.run_js("""
var logs = window.__apiLogs || [];
var results = [];
for (var i = 0; i < logs.length; i++) {
    var l = logs[i];
    if (l.method === 'POST' || l.method === 'PUT') {
        results.push(l.method + ' ' + l.url.substring(0, 100) + ' status=' + (l.status || 'pending'));
    }
}
return results.join('\\n') || 'no POST logs';
""")
print(all_logs)

# 找到保存按钮
print("\n保存按钮:")
save_btns = page.run_js("""
var all = document.querySelectorAll('button, span, div[role="button"]');
var results = [];
for (var i = 0; i < all.length; i++) {
    var text = (all[i].textContent || '').trim();
    var rect = all[i].getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && (text.indexOf('保存') !== -1 || text.indexOf('草稿') !== -1 || text.indexOf('发布') !== -1)) {
        results.push('[' + i + '] tag=' + all[i].tagName + ' class="' + (all[i].className || '').substring(0, 50) + '" text="' + text.substring(0, 30) + '" visible=' + (rect.width > 0));
    }
}
return results.join('\\n') || 'none';
""")
print(save_btns)

page.quit()
print("DONE")