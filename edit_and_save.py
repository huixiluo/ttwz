# -*- coding: utf-8 -*-
"""通过编辑已有草稿的方式保存新文章"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

def init_browser():
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
    if "profile" not in page.url.lower():
        page.quit()
        raise RuntimeError("Cookie登录失败")
    print("[OK] 登录成功")
    return page

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    new_title = art.get("title", "")[:30]
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"新文章标题: {new_title}")

    # 读取HTML内容
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body_html = ""
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

    page = init_browser()

    # 1. 进入草稿箱
    print("\n[1] 进入草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(5)

    # 2. 找到第一个草稿的"编辑"按钮并点击
    print("[2] 点击编辑按钮...")
    edit_result = page.run_js("""
var btns = document.querySelectorAll('button, span, div, a');
for (var i = 0; i < btns.length; i++) {
    var text = (btns[i].textContent || '').trim();
    var rect = btns[i].getBoundingClientRect();
    if (text === '编辑' && rect.width > 0 && rect.height > 0) {
        btns[i].scrollIntoView({block: 'center'});
        btns[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        return 'clicked';
    }
}
return 'not_found';
""")
    print(f"  编辑按钮: {edit_result}")
    time.sleep(5)

    # 3. 检查是否进入编辑页面
    current_url = page.url
    print(f"  当前URL: {current_url}")

    if 'graphic' not in current_url and 'publish' not in current_url and 'edit' not in current_url:
        print("  [FAIL] 未进入编辑页面")
        page.quit()
        return

    print("  [OK] 已进入编辑页面")

    # 等待ProseMirror
    for i in range(10):
        pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
        if pm > 0:
            break
        time.sleep(1)
    print(f"  ProseMirror: {pm}")

    # 4. 修改标题
    print("\n[3] 修改标题...")
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.clear()
        time.sleep(0.3)
        title_el.input(new_title)
        time.sleep(0.5)
        page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
        print(f"  标题已改为: {new_title}")

    # 5. 修改正文
    print("\n[4] 修改正文...")
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
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) editor.dispatchEvent(new Event('blur', {bubbles: true}));
""")
    time.sleep(1)
    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    print(f"  正文: {chars}字")

    # 6. 修改封面图
    print("\n[5] 修改封面图...")
    valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
    if valid:
        page.run_js("window.scrollTo(0, 0);")
        time.sleep(1)
        page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
        time.sleep(2)

        # 先检查是否有已存在的封面图，尝试删除
        page.run_js("""
var dels = document.querySelectorAll('.article-cover-delete, [class*="cover-delete"], [class*="cover-close"]');
for (var i = 0; i < dels.length; i++) {
    if (dels[i].getBoundingClientRect().width > 0) {
        dels[i].click();
        break;
    }
}
""")
        time.sleep(1)

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

    # 7. 等待保存
    print("\n[6] 等待保存...")
    # 注入网络监控
    page.run_js("""
window.__saveLogs = [];
var origFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url.url || '');
    if (urlStr.indexOf('publish') !== -1 || urlStr.indexOf('save') !== -1 || urlStr.indexOf('draft') !== -1) {
        var method = (options && options.method) || 'GET';
        var body = (options && options.body) ? (typeof options.body === 'string' ? options.body.substring(0, 1000) : JSON.stringify(options.body).substring(0, 1000)) : '';
        window.__saveLogs.push({url: urlStr, method: method, body: body, time: new Date().toISOString()});
    }
    return origFetch.apply(this, arguments).then(function(resp) {
        if (urlStr.indexOf('publish') !== -1 || urlStr.indexOf('save') !== -1 || urlStr.indexOf('draft') !== -1) {
            var clone = resp.clone();
            clone.text().then(function(t) {
                window.__saveLogs.push({url: urlStr, status: resp.status, response: t.substring(0, 500)});
            });
        }
        return resp;
    });
};
""")

    for i in range(30):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
return 'WAIT';
""")

        if i % 5 == 0:
            logs = page.run_js("""
var logs = window.__saveLogs || [];
return JSON.stringify(logs.slice(-3));
""")
            print(f"  [{i*2}s] {status} | logs: {logs}")

        if status == 'SAVED':
            print("\n[SUCCESS] 草稿已保存！")
            break

    # 最终日志
    print("\n=== 保存相关API日志 ===")
    final_logs = page.run_js("""
var logs = window.__saveLogs || [];
return JSON.stringify(logs, null, 2);
""")
    print(final_logs[:2000])

    page.quit()
    print("\nDONE")

if __name__ == "__main__":
    main()