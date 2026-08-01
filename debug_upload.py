# -*- coding: utf-8 -*-
"""调试上传：监控网络请求，深入分析保存失败原因"""
import os, json, time, re
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    manifest = json.load(f)

art = manifest[0]
title = art["title"]
html_path = art["html_file"]

print(f"文章: {title}")
print(f"HTML: {html_path}")

# 启动浏览器
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

# 注入fetch和XHR拦截器
page.run_js("""
window.__apiLogs = [];

// 拦截 fetch
var originalFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    var method = (options && options.method) || 'GET';
    var body = (options && options.body) ? options.body.substring(0, 500) : '';
    var logEntry = {url: urlStr, method: method, time: new Date().toISOString(), type: 'fetch'};
    window.__apiLogs.push(logEntry);
    return originalFetch.apply(this, arguments).then(function(response) {
        var clone = response.clone();
        clone.text().then(function(text) {
            logEntry.status = response.status;
            logEntry.response = text.substring(0, 500);
        }).catch(function(){});
        return response;
    });
};

// 拦截 XHR
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
        if (typeof body === 'string') {
            logEntry.reqBody = body.substring(0, 3000);
        } else if (body instanceof FormData) {
            var parts = [];
            body.forEach(function(v, k) { parts.push(k + '=' + (typeof v === 'string' ? v.substring(0, 200) : '[binary]')); });
            logEntry.reqBody = 'FormData: ' + parts.join('&').substring(0, 3000);
        } else {
            logEntry.reqBody = 'typeof=' + typeof body;
        }
    }
    window.__apiLogs.push(logEntry);
    xhr.addEventListener('load', function() {
        logEntry.status = xhr.status;
        logEntry.response = (xhr.responseText || '').substring(0, 500);
    });
    return origXHRSend.apply(this, arguments);
};

console.log('[DEBUG] fetch + XHR interceptors installed');
""")

# 填写标题
print("\n[1] 填写标题...")
title_text = title[:30]
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.clear()
    title_el.input(title_text)
    time.sleep(0.5)
    # 触发React事件
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
}
""")
    print(f"  标题: {title_text}")
else:
    print("  找不到标题输入框")

# 填写正文
print("\n[2] 填写正文...")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# 提取body内容
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
if body_match:
    body = body_match.group(1)
    result_parts = []
    for m in re.finditer(
        r'(<p>(.*?)</p>)|'
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            para_text = m.group(2)
            para_text = re.sub(r'<[^>]+>', '', para_text)
            result_parts.append(f'<p>{para_text}</p>')
        elif m.group(4):
            result_parts.append(f'<p><img src="{m.group(4)}" /></p>')
    
    body_html = "\n".join(result_parts)
    
    result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'not_found';
editor.innerHTML = '';
editor.focus();
var dt = new DataTransfer();
dt.setData('text/html', {json.dumps(body_html)});
var pasteEvent = new ClipboardEvent('paste', {{
  bubbles: true,
  cancelable: true,
  clipboardData: dt
}});
editor.dispatchEvent(pasteEvent);
return 'ok';
""")
    print(f"  正文结果: {result}")
    
    # 检查内容
    para_count = page.run_js("return document.querySelectorAll('.ProseMirror p').length;")
    img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  段落数: {para_count}, 图片数: {img_count}")

# 等待自动保存
print("\n[3] 等待并监控保存...")
for i in range(15):
    time.sleep(2)
    status = page.run_js("""
var body = document.body.innerText;
var results = [];
if (body.indexOf('草稿已保存') !== -1) results.push('SAVED: 草稿已保存');
if (body.indexOf('已保存') !== -1) results.push('SAVED: 已保存');
if (body.indexOf('保存成功') !== -1) results.push('SAVED: 保存成功');
if (body.indexOf('草稿保存中') !== -1) results.push('SAVING: 草稿保存中');
if (body.indexOf('保存失败') !== -1) results.push('FAIL: 保存失败');

// 获取API日志（只显示publish相关的）
var apiLogs = window.__apiLogs || [];
var saveLogs = [];
for (var j = 0; j < apiLogs.length; j++) {
    var log = apiLogs[j];
    if (log.url.indexOf('publish') !== -1 || log.url.indexOf('save') !== -1) {
        saveLogs.push(log.method + ' ' + log.url.substring(0, 80) + ' status=' + (log.status || 'pending') + ' reqBody=' + (log.reqBody || 'none').substring(0, 300) + ' resp=' + (log.response || 'none').substring(0, 200));
    }
}
if (results.length === 0) results.push('idle');
results.push('API_LOGS: ' + (saveLogs.length > 0 ? saveLogs.join(' | ') : 'none'));
return results.join('\\n');
""")
    print(f"  [{i+1}] {status}")
    if 'SAVED' in status:
        break

# 查看所有API日志
print("\n[4] 所有API日志:")
all_logs = page.run_js("""
var logs = window.__apiLogs || [];
var results = [];
for (var i = 0; i < logs.length; i++) {
    var log = logs[i];
    results.push(log.method + ' ' + log.url.substring(0, 100) + ' status=' + (log.status || 'pending'));
}
return results.join('\\n');
""")
print(all_logs)

page.quit()