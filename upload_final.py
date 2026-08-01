# -*- coding: utf-8 -*-
"""最终版上传：监控网络请求，尝试多种保存方式"""
import os, re, json, time
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def init_browser():
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.headless(True)
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
    if "profile" not in page.url.lower() and "graphic" not in page.url.lower():
        page.quit()
        raise RuntimeError("Cookie登录失败")
    print("  [OK] 登录成功")
    return page

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    title = art.get("title", "")
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"文章: {title}")

    page = init_browser()
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

    # === 注入网络监控 ===
    page.run_js("""
window.__apiLogs = [];
var origFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    var method = (options && options.method) || 'GET';
    var logEntry = {url: urlStr, method: method, time: new Date().toISOString(), type: 'fetch'};
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
var origXHROpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    this._method = method;
    this._url = typeof url === 'string' ? url : (url.toString ? url.toString() : '');
    return origXHROpen.apply(this, arguments);
};
var origXHRSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(body) {
    var xhr = this;
    var logEntry = {url: xhr._url || '', method: xhr._method || 'GET', time: new Date().toISOString(), type: 'xhr'};
    if (body) {
        if (typeof body === 'string') logEntry.reqBody = body.substring(0, 1000);
        else if (body instanceof FormData) {
            var parts = [];
            body.forEach(function(v,k) { parts.push(k + '=' + (typeof v === 'string' ? v.substring(0,200) : '[binary]')); });
            logEntry.reqBody = 'FormData: ' + parts.join('&').substring(0, 1000);
        }
    }
    window.__apiLogs.push(logEntry);
    xhr.addEventListener('load', function() {
        logEntry.status = xhr.status;
        logEntry.response = (xhr.responseText || '').substring(0, 500);
    });
    return origXHRSend.apply(this, arguments);
};
console.log('[MONITOR] Network interceptors installed');
""")
    print("  网络监控已安装")

    # === 第1步：填标题 ===
    print("\n=== 填标题 ===")
    title_text = title[:30]
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.clear()
        title_el.input(title_text)
        time.sleep(0.5)
        page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
        print(f"  标题: {title_text}")

    # === 第2步：上传封面 ===
    print("\n=== 上传封面 ===")
    valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
    if valid:
        page.run_js("window.scrollTo(0, 0);")
        time.sleep(1)
        page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
        time.sleep(2)

        # 选三图
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

        add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
        print(f"  add按钮: {add_count}")

        for ci, cf in enumerate(valid):
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

            file_input = None
            for _ in range(15):
                all_inputs = page.eles('tag:input@type=file')
                for fi in all_inputs:
                    try:
                        accept = fi.attr('accept') or ''
                        if 'image' in accept:
                            rect = fi.rect
                            if rect.size[0] > 0 and rect.size[1] > 0:
                                file_input = fi
                                break
                    except:
                        pass
                if file_input:
                    break
                time.sleep(0.5)

            if file_input:
                file_input.input(cf)
                time.sleep(3)
                print(f"  封面{ci+1}: ✓")
            else:
                print(f"  封面{ci+1}: 找不到控件")

    # === 第3步：填正文 ===
    print("\n=== 填正文 ===")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
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
                para_text = re.sub(r'<[^>]+>', '', m.group(2))
                result_parts.append(f'<p>{para_text}</p>')
            elif m.group(4):
                result_parts.append(f'<p><img src="{m.group(4)}" /></p>')
        body_html = "\n".join(result_parts)

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

        # 触发blur
        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) editor.dispatchEvent(new Event('blur', {bubbles: true}));
var title = document.querySelector('textarea[placeholder*="文章标题"]');
if (title) { title.focus(); setTimeout(function() { title.blur(); }, 100); }
""")
        time.sleep(1)

        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
        imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
        print(f"  正文: {chars}字, {imgs}张图片")

    # === 第4步：等待保存并监控 ===
    print("\n=== 等待保存（监控网络请求）===")
    for i in range(30):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED';
    if (t.indexOf('草稿保存中') !== -1) return 'SAVING';
}
return 'IDLE';
""")
        if i % 5 == 0 or status != 'IDLE':
            logs = page.run_js("""
var logs = window.__apiLogs || [];
var recent = logs.slice(-5);
var result = [];
for (var i = 0; i < recent.length; i++) {
    var l = recent[i];
    result.push(l.method + ' ' + l.url.substring(0, 80) + ' status=' + (l.status || 'pending') + ' resp=' + (l.response || '').substring(0, 100));
}
return result.join('\\n') || 'no logs';
""")
            print(f"  [{i*2}s] {status}")
            if logs and logs != 'no logs':
                print(f"    API: {logs}")

        if status == 'SAVED':
            print("\n[SUCCESS] 草稿已保存！")
            break

        if status == 'IDLE' and i > 3:
            # 尝试点击保存
            page.run_js("""
var btns = document.querySelectorAll('button, span');
for (var i = 0; i < btns.length; i++) {
    var t = (btns[i].textContent || '').trim();
    if (t === '保存' || t === '存草稿' || t.indexOf('保存草稿') !== -1) {
        btns[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        break;
    }
}
""")
            print(f"    已点击保存按钮")

    # 输出最终网络日志
    print("\n=== 最终网络日志 ===")
    final_logs = page.run_js("""
var logs = window.__apiLogs || [];
var result = [];
for (var i = 0; i < logs.length; i++) {
    var l = logs[i];
    if (l.url.indexOf('save') !== -1 || l.url.indexOf('draft') !== -1 || l.url.indexOf('publish') !== -1 || l.url.indexOf('article') !== -1) {
        result.push(l.method + ' ' + l.url.substring(0, 100) + ' status=' + (l.status || 'pending') + ' resp=' + (l.response || '').substring(0, 200));
    }
}
return result.join('\\n') || 'no relevant logs';
""")
    print(final_logs)

    # 检查页面最终状态
    final_status = page.run_js("return document.body.innerText.substring(0, 500);")
    print(f"\n页面状态: {final_status[:300]}")

    page.quit()
    print("\nDONE")

if __name__ == "__main__":
    main()