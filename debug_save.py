# -*- coding: utf-8 -*-
"""监控网络请求，调试保存"""
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

page.get("https://mp.toutiao.com/profile_v4/index")
time.sleep(3)
page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(5)

# 关闭弹窗
try:
    close_btn = page.ele('text:关闭', timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 注入fetch拦截器，在页面加载时就注入
page.run_js("""
window.__fetchLogs = [];
var originalFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    window.__fetchLogs.push({url: urlStr, time: new Date().toISOString(), method: (options && options.method) || 'GET'});
    console.log('[FETCH] ' + urlStr);
    return originalFetch.apply(this, arguments).then(function(response) {
        var clone = response.clone();
        clone.text().then(function(text) {
            if (text && text.length > 0) {
                window.__fetchLogs.push({url: urlStr, response: text.substring(0, 300), status: response.status});
                console.log('[FETCH RESP] ' + urlStr + ' status=' + response.status + ' body=' + text.substring(0, 200));
            }
        }).catch(function(){});
        return response;
    });
};
console.log('[DEBUG] fetch interceptor installed');
""")

# 填写标题
print("=== 填写标题 ===")
title = "退货先给码，钱货两空，你的取件码还安全吗？"
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if title_el:
    title_el.clear()
    title_el.input(title)
    print(f"标题: {title}")
time.sleep(1)

# 填写正文
print("=== 填写正文 ===")
page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'not_found';
editor.innerHTML = '';
editor.focus();
var dt = new DataTransfer();
dt.setData('text/html', '<p>测试段落1：退货时千万别急着给取件码。</p><p>测试段落2：很多人接到快递员电话就急着报码。</p>');
var pasteEvent = new ClipboardEvent('paste', {
  bubbles: true,
  cancelable: true,
  clipboardData: dt
});
editor.dispatchEvent(pasteEvent);
return 'ok';
""")
time.sleep(3)

# 检查网络请求
print("\n=== 网络请求日志 ===")
logs = page.run_js("""
var results = [];
var logs = window.__fetchLogs || [];
for (var i = 0; i < logs.length; i++) {
    var log = logs[i];
    if (log.response) {
        results.push(log.url + ' -> ' + log.response);
    } else if (log.url && (log.url.indexOf('draft') !== -1 || log.url.indexOf('save') !== -1 || log.url.indexOf('article') !== -1 || log.url.indexOf('content') !== -1)) {
        results.push(log.url + ' (no response yet)');
    }
}
return results.join('\\n') || 'no relevant logs';
""")
print(logs)

# 等待并检查草稿状态
print("\n=== 等待保存 ===")
for i in range(10):
    time.sleep(2)
    status = page.run_js("""
var results = [];
var spans = document.querySelectorAll('span');
for (var i = 0; i < spans.length; i++) {
    var text = spans[i].textContent.trim();
    if (text.indexOf('草稿') !== -1) results.push(text);
}
var body = document.body.innerText;
if (body.indexOf('保存失败') !== -1) results.push('保存失败');
if (body.indexOf('已保存') !== -1) results.push('已保存');
return results.join(' | ');
""")
    print(f"  {i+1}: {status}")
    
    if '已保存' in str(status):
        break

# 最终检查网络请求
print("\n=== 最终网络请求 ===")
logs2 = page.run_js("""
var results = [];
var logs = window.__fetchLogs || [];
var relevant = [];
for (var i = 0; i < logs.length; i++) {
    var log = logs[i];
    if (log.url && (log.url.indexOf('draft') !== -1 || log.url.indexOf('save') !== -1 || log.url.indexOf('article') !== -1 || log.url.indexOf('content') !== -1 || log.url.indexOf('publish') !== -1)) {
        relevant.push(log);
    }
}
results.push('相关请求数: ' + relevant.length);
for (var i = 0; i < relevant.length; i++) {
    var r = relevant[i];
    results.push(r.time + ' ' + r.method + ' ' + r.url.substring(0, 100));
    if (r.response) {
        results.push('  -> ' + r.response.substring(0, 200));
    }
}
return results.join('\\n');
""")
print(logs2)

page.quit()