# -*- coding: utf-8 -*-
"""测试：使用DrissionPage actions触发真实键盘事件"""
import os, re, json, time
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
    var logEntry = {url: urlStr, method: method, time: new Date().toISOString()};
    window.__apiLogs.push(logEntry);
    return origFetch.apply(this, arguments).then(function(resp) {
        var clone = resp.clone();
        clone.text().then(function(t) {
            logEntry.status = resp.status;
            logEntry.response = t.substring(0, 500);
        }).catch(function(){});
        return resp;
    });
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

# 填正文
page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (editor) {{
    editor.focus();
    editor.innerHTML = '';
    var dt = new DataTransfer();
    dt.setData('text/html', {json.dumps(body_html)});
    editor.dispatchEvent(new ClipboardEvent('paste', {{
        bubbles: true, cancelable: true, clipboardData: dt
    }}));
    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
    editor.dispatchEvent(new Event('change', {{bubbles: true}}));
}}
""")
time.sleep(2)
chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
print(f"正文: {chars}字, {imgs}张图片")

# 使用DrissionPage actions在编辑器里输入空格再删除
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(0.5)
    editor.input(" ")
    time.sleep(0.3)
    page.actions.key_down('BACKSPACE').key_up('BACKSPACE').perform()
    time.sleep(0.5)
    editor.input(" ")
    time.sleep(0.3)
    page.actions.key_down('BACKSPACE').key_up('BACKSPACE').perform()
    time.sleep(0.5)
    print("编辑器输入事件已触发")

# 上传封面
print("\n上传封面...")
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if valid:
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)
    page.run_js("""
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    if (radios[i].value === '3') {
        radios[i].click();
        radios[i].checked = true;
        radios[i].dispatchEvent(new Event('change', {bubbles: true}));
        return;
    }
}
""")
    time.sleep(3)

    for ci, cf in enumerate(valid):
        print(f"  封面{ci+1}: {os.path.basename(cf)}...")
        page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) {
    add.scrollIntoView({block: 'center'});
    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
        add.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    });
}
""")
        time.sleep(2)
        fi = None
        for _ in range(15):
            for inp in page.eles('tag:input@type=file'):
                try:
                    if 'image' in (inp.attr('accept') or '') and inp.rect.size[0] > 0:
                        fi = inp
                        break
                except:
                    pass
            if fi:
                break
            time.sleep(0.5)
        if fi:
            fi.input(cf)
            time.sleep(3)
            print(f"  封面{ci+1}: ✓")
        else:
            for inp in page.eles('tag:input@type=file'):
                try:
                    inp.input(cf)
                    time.sleep(3)
                    print(f"  封面{ci+1}: ✓ (兜底)")
                    break
                except:
                    continue
            else:
                print(f"  封面{ci+1}: 未找到")

# 触发保存
print("\n触发保存...")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.click()
    time.sleep(0.3)
    title_el.input(" ")
    time.sleep(0.3)
    page.actions.key_down('BACKSPACE').key_up('BACKSPACE').perform()
    time.sleep(0.5)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")

# 等待保存
print("等待保存...")
for i in range(30):
    time.sleep(1)
    status = page.run_js("""
var body = document.body.innerText;
var results = [];
if (body.indexOf('草稿已保存') !== -1) results.push('SAVED');
if (body.indexOf('已保存') !== -1) results.push('SAVED');
if (body.indexOf('保存成功') !== -1) results.push('SAVED');
if (body.indexOf('草稿保存中') !== -1) results.push('SAVING');
if (results.length === 0) results.push('idle');
var logs = window.__apiLogs || [];
var saveLogs = [];
for (var j = 0; j < logs.length; j++) {
    var l = logs[j];
    if (l.url.indexOf('publish') !== -1 || l.url.indexOf('save') !== -1 || l.url.indexOf('draft') !== -1) {
        saveLogs.push(l.method + ' ' + l.url.substring(0, 80) + ' status=' + (l.status || 'pending') + ' resp=' + (l.response || '').substring(0, 200));
    }
}
results.push('API: ' + (saveLogs.length > 0 ? saveLogs.join(' | ') : 'none'));
return results.join(' | ');
""")
    if i % 5 == 0:
        print(f"  [{i}s] {status}")
    if 'SAVED' in status:
        print(f"\n[SUCCESS] {i+1}s")
        break
else:
    print("\n[FAIL] 30秒未检测到保存")

# 最终验证
print("\n验证草稿箱...")
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;")
if title[:8] in draft_text:
    idx = draft_text.find(title[:8])
    print(f"[SUCCESS] 文章在草稿箱中!")
    print(f"  {draft_text[idx:idx+120]}")
else:
    print("[FAIL] 未找到")
    print(f"  草稿箱: {draft_text[:500]}")

page.quit()
print("DONE")