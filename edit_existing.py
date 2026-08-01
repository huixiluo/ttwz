# -*- coding: utf-8 -*-
"""编辑已有草稿：找到"测试文章保存功能"并编辑"""
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
    print("[OK] 登录成功")
    return page

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    real_title = art.get("title", "")[:30]
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"标题: {real_title}")

    # 读取HTML正文
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

    # 2. 查找草稿列表
    print("[2] 查找草稿...")
    draft_info = page.run_js("""
var items = document.querySelectorAll('[class*="draft"], [class*="list-item"], [class*="article-item"], li, tr');
var result = [];
for (var i = 0; i < Math.min(items.length, 20); i++) {
    var text = (items[i].textContent || '').trim();
    var rect = items[i].getBoundingClientRect();
    if (rect.width > 100 && text.length > 3) {
        result.push('[' + i + '] ' + text.substring(0, 100));
    }
}
return result.join('\\n');
""")
    print(f"草稿列表:\n{draft_info[:500]}")

    # 3. 点击"编辑"按钮 - 使用DrissionPage原生点击
    print("\n[3] 点击编辑按钮...")
    # 先获取所有"编辑"元素的详细信息
    edit_info = page.run_js("""
var all = document.querySelectorAll('span, button, div, a');
var result = [];
for (var i = 0; i < all.length; i++) {
    var text = (all[i].textContent || '').trim();
    var rect = all[i].getBoundingClientRect();
    if (text === '编辑' && rect.width > 0) {
        result.push('[' + i + '] tag=' + all[i].tagName + 
            ' class="' + (all[i].className || '').substring(0, 50) + '"' +
            ' href=' + (all[i].getAttribute('href') || 'none') +
            ' w=' + rect.width + ' h=' + rect.height);
    }
}
return result.join('\\n');
""")
    print(f"  编辑按钮:\n{edit_info}")

    # 使用DrissionPage查找并点击
    try:
        edit_btn = page.ele('text:编辑', timeout=5)
        if edit_btn:
            print(f"  找到编辑按钮: {edit_btn}")
            edit_btn.click()
            time.sleep(5)
            print(f"  当前URL: {page.url}")
        else:
            print("  DrissionPage未找到编辑按钮")
    except Exception as e:
        print(f"  点击异常: {e}")

    # 检查是否进入编辑页
    if 'graphic' in page.url or 'publish' in page.url:
        print("  [OK] 已进入编辑页面")

        # 等待ProseMirror
        for i in range(10):
            pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
            if pm > 0:
                break
            time.sleep(1)
        print(f"  ProseMirror: {pm}")

        # 修改标题
        print("\n[4] 修改标题...")
        title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
        if not title_el:
            title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
        if title_el:
            title_el.click()
            time.sleep(0.3)
            # 全选清除
            page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.select(); }
""")
            time.sleep(0.2)
            title_el.clear()
            time.sleep(0.2)
            title_el.input(real_title)
            time.sleep(0.5)
            page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
            print(f"  标题: {real_title}")

        # 等待标题保存
        for i in range(15):
            time.sleep(2)
            s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'WAIT';
""")
            if s == 'SAVED':
                print(f"  [OK] 标题保存成功 ({i*2}s)")
                break
            if i % 3 == 0:
                print(f"  [{i*2}s] {s}")

        # 修改正文
        print("\n[5] 修改正文...")
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
}}
""")
        time.sleep(2)
        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
        print(f"  正文: {chars}字")

        # 触发标题修改来保存
        print("  触发保存...")
        title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
        if not title_el:
            title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
        if title_el:
            title_el.click()
            time.sleep(0.3)
            title_el.input(" ")
            time.sleep(0.3)
            page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")

        # 等待保存
        for i in range(20):
            time.sleep(2)
            s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'WAIT';
""")
            if s == 'SAVED':
                print(f"  [SUCCESS] 正文保存成功！({i*2}s)")
                break
            if i % 5 == 0:
                print(f"  [{i*2}s] {s}")

        # 上传封面
        print("\n[6] 上传封面...")
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
                            if 'image' in (fi.attr('accept') or ''):
                                if fi.rect.size[0] > 0:
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
                    print(f"  封面{ci+1}: 未找到")

        # 触发保存
        print("  触发保存...")
        title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
        if not title_el:
            title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
        if title_el:
            title_el.click()
            time.sleep(0.3)
            title_el.input(" ")
            time.sleep(0.3)
            page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")

        for i in range(10):
            time.sleep(2)
            s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'WAIT';
""")
            if s == 'SAVED':
                print(f"  [SUCCESS] 全部保存成功！({i*2}s)")
                break
            if i % 3 == 0:
                print(f"  [{i*2}s] {s}")

    else:
        print("  [FAIL] 未进入编辑页面")

    # 最终检查草稿箱
    print("\n[7] 检查草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(5)
    draft_text = page.run_js("return document.body.innerText.substring(0, 800);")
    if real_title[:8] in draft_text:
        print("[SUCCESS] 文章已在草稿箱中！")
    else:
        print("[CHECK] 草稿箱内容:")
        print(draft_text[:400])

    page.quit()
    print("DONE")

if __name__ == "__main__":
    main()