# -*- coding: utf-8 -*-
"""测试：使用DrissionPage真实点击+键盘输入，不用JS注入"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

co = ChromiumOptions()
# 不使用headless，看看能不能看到真实的页面状态
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
time.sleep(5)  # 等待更长时间让页面完全加载

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

# 步骤1: 先点击编辑器区域，确保聚焦
print("[1] 聚焦编辑器...")
try:
    editor = page.ele('.ProseMirror', timeout=10)
    if editor:
        editor.click()
        time.sleep(1)
        print("  编辑器已聚焦")
except Exception as e:
    print(f"  聚焦失败: {e}")

# 步骤2: 用DrissionPage填写标题（真实键盘输入）
print("[2] 填写标题...")
title = "测试真实输入保存"
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.click()
    time.sleep(0.5)
    title_el.clear()
    time.sleep(0.3)
    title_el.input(title)
    time.sleep(1)
    print(f"  标题: {title}")
else:
    print("  找不到标题框")

# 步骤3: 用DrissionPage在编辑器中输入文字（真实键盘）
print("[3] 填写正文...")
try:
    editor = page.ele('.ProseMirror', timeout=5)
    if editor:
        editor.click()
        time.sleep(0.5)
        # 输入几段文字
        editor.input("这是第一段测试内容，用于验证真实键盘输入是否能触发保存。\n")
        time.sleep(0.5)
        editor.input("这是第二段内容，继续测试头条号的草稿保存功能。\n")
        time.sleep(0.5)
        editor.input("这是第三段内容，希望这次能成功保存。")
        time.sleep(1)
        
        # 检查编辑器内容
        text = page.run_js("return document.querySelector('.ProseMirror').innerText;")
        print(f"  编辑器内容: {text[:100]}...")
except Exception as e:
    print(f"  输入失败: {e}")

# 步骤4: 等待自动保存
print("\n[4] 等待自动保存...")
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
        publishLogs.push('status=' + (log.status || 'pending') + ' resp=' + (log.response || 'none').substring(0, 200));
    }
}
if (results.length === 0) results.push('idle');
results.push('API: ' + (publishLogs.length > 0 ? publishLogs.join(' | ') : 'none'));
return results.join('\\n');
""")
    print(f"  [{i+1}] {status}")
    if 'SAVED' in status:
        print("\n[SUCCESS] 保存成功！")
        break

# 如果还是失败，尝试点击保存按钮
print("\n[5] 尝试手动点击保存按钮...")
save_clicked = page.run_js("""
var allBtns = document.querySelectorAll('button, span, div[role="button"]');
for (var i = 0; i < allBtns.length; i++) {
    var btn = allBtns[i];
    var text = (btn.textContent || '').trim();
    if (text.indexOf('保存') !== -1 || text.indexOf('草稿') !== -1) {
        var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
        btn.dispatchEvent(evt);
        return 'clicked: ' + text;
    }
}
return 'not_found';
""")
print(f"  结果: {save_clicked}")

# 再次等待
for i in range(10):
    time.sleep(2)
    status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'idle';
""")
    print(f"  [{i+1}] {status}")
    if status == 'SAVED':
        print("\n[SUCCESS]")
        break

page.quit()