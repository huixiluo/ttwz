# -*- coding: utf-8 -*-
"""测试：编辑已有草稿并保存，验证账号是否有创建限制"""
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
    if (body && typeof body === 'string') logEntry.reqBody = body.substring(0, 2000);
    window.__apiLogs.push(logEntry);
    xhr.addEventListener('load', function() {
        logEntry.status = xhr.status;
        logEntry.response = (xhr.responseText || '').substring(0, 500);
    });
    return origXHRSend.apply(this, arguments);
};
""")

# 找到第一个"编辑"按钮并点击，进入编辑页面
print("[1] 点击编辑按钮进入已有草稿...")
edit_clicked = page.run_js("""
var btns = document.querySelectorAll('button, span, div, a');
for (var i = 0; i < btns.length; i++) {
    var text = (btns[i].textContent || '').trim();
    if (text === '编辑' && btns[i].getBoundingClientRect().width > 0) {
        btns[i].scrollIntoView({block: 'center'});
        var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
        btns[i].dispatchEvent(evt);
        return 'clicked';
    }
}
return 'not_found';
""")
print(f"  结果: {edit_clicked}")

time.sleep(5)
print(f"  当前URL: {page.url}")

# 检查是否进入了编辑页面
if 'graphic' in page.url or 'publish' in page.url or 'edit' in page.url:
    print("  [OK] 已进入编辑页面")
    
    # 在标题末尾加一个空格再删除，触发修改
    print("\n[2] 触发修改...")
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=3)
    if title_el:
        title_el.input(" ")
        time.sleep(0.5)
        # 触发backspace删除空格
        page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
        print("  已触发修改")
    
    # 等待保存
    print("\n[3] 等待保存...")
    for i in range(15):
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
            print("\n[SUCCESS] 已有草稿可以保存！问题可能是新建草稿限制。")
            break
        if 'FAIL' in status:
            print("\n[FAIL] 已有草稿也无法保存！可能是Cookie或账号问题。")
else:
    print("  [FAIL] 未能进入编辑页面")

page.quit()