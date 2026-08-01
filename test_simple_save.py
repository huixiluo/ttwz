# -*- coding: utf-8 -*-
"""最简测试：真实键盘输入，测试保存是否工作"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

page.get("https://mp.toutiao.com")
time.sleep(2)
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
print(f"Login: {page.url}")

# 注入网络监控
page.run_js("""
window.__apiLogs = [];
var origFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    var method = (options && options.method) || 'GET';
    var body = (options && options.body) ? (typeof options.body === 'string' ? options.body.substring(0, 500) : '') : '';
    var logEntry = {url: urlStr, method: method, body: body, time: new Date().toISOString()};
    window.__apiLogs.push(logEntry);
    return origFetch.apply(this, arguments).then(function(resp) {
        var clone = resp.clone();
        clone.text().then(function(t) {
            logEntry.status = resp.status;
            logEntry.response = t.substring(0, 500);
        });
        return resp;
    });
};
""")

page.get(PUBLISH_URL)
time.sleep(6)

# 等待ProseMirror
for i in range(10):
    pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
    if pm > 0:
        break
    time.sleep(1)
print(f"ProseMirror: {pm}")

# 关闭弹窗
try:
    close_btn = page.ele("text:关闭", timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 测试1: 只填标题，用真实键盘输入
print("\n=== 测试1: 填标题 ===")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if title_el:
    title_el.click()
    time.sleep(0.5)
    title_el.input("测试文章保存功能")
    time.sleep(1)
    # blur
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
    print("标题已填写: 测试文章保存功能")
    time.sleep(3)

# 检查保存状态
status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'IDLE';
""")
print(f"填标题后状态: {status}")

# 测试2: 在编辑器里输入文字
print("\n=== 测试2: 填正文 ===")
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(1)
    editor.input("这是第一段测试内容。用于验证头条号的草稿保存功能是否正常工作。")
    time.sleep(1)
    editor.input("\n")
    time.sleep(0.5)
    editor.input("这是第二段内容。如果保存成功，说明问题出在之前的JS填充方式上。")
    time.sleep(2)
    print("正文已输入")
else:
    print("找不到编辑器")

# 检查保存状态
for i in range(20):
    time.sleep(2)
    status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
    if (t.indexOf('草稿保存中') !== -1) return 'SAVING';
}
return 'IDLE';
""")
    print(f"  [{i*2}s] {status}")
    if status == 'SAVED' or status == 'SAVED_BTN':
        print("\n[SUCCESS] 真实输入可以保存！")
        break
    if status == 'IDLE' and i > 3:
        # 点击保存按钮
        page.run_js("""
var btns = document.querySelectorAll('button, span');
for (var i = 0; i < btns.length; i++) {
    var t = (btns[i].textContent || '').trim();
    if (t === '保存' || t.indexOf('保存草稿') !== -1) {
        btns[i].click();
        break;
    }
}
""")

# 输出API日志
print("\n=== API日志 ===")
logs = page.run_js("""
var logs = window.__apiLogs || [];
var result = [];
for (var i = 0; i < logs.length; i++) {
    var l = logs[i];
    if (l.url.indexOf('publish') !== -1 || l.url.indexOf('save') !== -1 || l.url.indexOf('draft') !== -1) {
        result.push(l.method + ' ' + l.url.substring(0, 100) + ' status=' + (l.status || 'pending') + ' resp=' + (l.response || '').substring(0, 200));
    }
}
return result.join('\\n') || 'no relevant logs';
""")
print(logs)

page.quit()
print("\nDONE")