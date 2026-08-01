# -*- coding: utf-8 -*-
"""修复版上传：修复封面图上传（dispatchEvent）和保存草稿"""
import os, re, json, time, base64
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"


def load_cookies():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def init_browser():
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.headless(True)

    page = ChromiumPage(co)
    page.get("https://mp.toutiao.com")
    time.sleep(2)

    cookies = load_cookies()
    for name, value in cookies.items():
        try:
            page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        except Exception:
            pass

    page.get("https://mp.toutiao.com")
    time.sleep(3)
    print(f"  URL: {page.url}")

    if "profile" not in page.url.lower() and "graphic" not in page.url.lower():
        print("  [错误] Cookie登录失败")
        page.quit()
        raise RuntimeError("Cookie登录失败")

    print("  [OK] 登录成功")
    return page


def fill_title_and_content(page, title, html_path):
    """先填正文再填标题"""
    title_text = title[:30] if len(title) > 30 else title

    # 第1步：填正文
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_match:
        print("  [错误] 未找到正文")
        return False

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

    result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'editor_not_found';
editor.innerHTML = '';
editor.focus();
var dt = new DataTransfer();
dt.setData('text/html', {json.dumps(body_html)});
editor.dispatchEvent(new ClipboardEvent('paste', {{
    bubbles: true, cancelable: true, clipboardData: dt
}}));
return 'content_ok';
""")
    if 'editor_not_found' in str(result):
        print("  [错误] 找不到编辑器")
        return False
    print(f"  正文已填写 ({result})")
    time.sleep(1)

    # 第2步：填标题
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        print("  [错误] 找不到标题输入框")
        return False

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
    print(f"  标题已填写: {title_text}")

    time.sleep(2)
    total_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  正文: 约{total_chars}字, {img_count}张图片")
    return True


def upload_cover_images(page, cover_paths):
    """上传封面图（三图模式）- 使用dispatchEvent触发"""
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("  [封面] 无有效封面图文件")
        return False

    print(f"  [封面] 准备上传{len(valid)}张...")

    # 1. 先滚动到页面顶部，确保封面区域被渲染
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)

    # 2. 滚动到封面区域
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)

    # 3. 选择三图模式 - 点击radio并触发change事件
    select_result = page.run_js("""
// 先尝试点击radio按钮
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    if (radios[i].value === '3') {
        radios[i].click();
        radios[i].checked = true;
        radios[i].dispatchEvent(new Event('change', {bubbles: true}));
        radios[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        return 'clicked_radio';
    }
}
// 兜底：点击label
var labels = document.querySelectorAll('label');
for (var i = 0; i < labels.length; i++) {
    if ((labels[i].textContent || '').indexOf('三图') !== -1) {
        labels[i].click();
        labels[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        return 'clicked_label';
    }
}
return 'not_found';
""")
    print(f"  [封面] 三图模式: {select_result}")
    time.sleep(3)

    # 3. 检查三图模式的add按钮
    add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
    print(f"  [封面] add按钮数量: {add_count}")

    # 4. 逐张上传封面
    success_count = 0
    for ci, cf in enumerate(valid):
        print(f"    封面{ci+1}: 上传 {os.path.basename(cf)}...")

        # 等待add按钮出现
        for _ in range(10):
            add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
            if add_count > 0:
                break
            time.sleep(1)

        if add_count == 0:
            print(f"    封面{ci+1}: add按钮未出现，跳过")
            continue

        # 使用dispatchEvent点击add按钮
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

        # 查找文件输入框
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
                except Exception:
                    pass
            if file_input:
                break
            time.sleep(0.5)

        if file_input:
            file_input.input(cf)
            time.sleep(3)
            success_count += 1
            print(f"    封面{ci+1}: 上传成功 ✓")
        else:
            # 兜底：尝试所有file input
            all_inputs = page.eles('tag:input@type=file')
            for inp in all_inputs:
                try:
                    inp.input(cf)
                    time.sleep(3)
                    success_count += 1
                    print(f"    封面{ci+1}: 上传成功(兜底) ✓")
                    break
                except Exception:
                    continue
            else:
                print(f"    封面{ci+1}: 找不到上传控件")

    print(f"  [封面] 成功 {success_count}/{len(valid)} 张")
    return success_count > 0


def save_draft(page):
    """保存草稿"""
    print("  保存草稿...")
    time.sleep(3)

    # 检查当前状态
    status = page.run_js("""
var allBtns = document.querySelectorAll('button, span');
for (var i = 0; i < allBtns.length; i++) {
    var text = (allBtns[i].textContent || '').trim();
    if (text.indexOf('草稿已保存') !== -1 || text.indexOf('已保存') !== -1) return 'saved';
    if (text.indexOf('草稿保存中') !== -1) return 'saving';
}
return 'idle';
""")
    print(f"  初始状态: {status}")

    if status == 'saved':
        print("  [OK] 草稿已自动保存")
        return True

    if status == 'saving':
        for _ in range(30):
            time.sleep(2)
            s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1) return 'saved';
return null;
""")
            if s:
                print(f"  [OK] 草稿保存成功")
                return True
        print("  [警告] 保存超时")

    # 主动点击保存按钮
    for attempt in range(3):
        page.run_js("""
var allBtns = document.querySelectorAll('button, span, div[role="button"]');
for (var i = 0; i < allBtns.length; i++) {
    var btn = allBtns[i];
    var text = (btn.textContent || '').trim();
    var rect = btn.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && 
        (text === '保存' || text === '存草稿' || text.indexOf('保存草稿') !== -1)) {
        btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        return;
    }
}
""")
        print(f"  已点击保存按钮(尝试{attempt+1})")

        for _ in range(20):
            time.sleep(1.5)
            saved = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1) return 'saved';
return null;
""")
            if saved:
                print(f"  [OK] 草稿保存成功")
                return True

        if attempt < 2:
            print("  重试...")
            time.sleep(2)

    print("  [警告] 多次尝试后仍未确认保存")
    return False


def main():
    if not os.path.exists(MANIFEST_FILE):
        print(f"清单文件不存在: {MANIFEST_FILE}")
        return

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传\n")

    page = init_browser()

    for idx, art in enumerate(articles, 1):
        title = art.get("title", "")
        cover_files = art.get("cover_files", [])
        category = art.get("category", "")
        html_path = art.get("html_file", "")

        print(f"\n[{idx}/{len(articles)}] {category} | {title}")

        page.get(PUBLISH_URL)
        time.sleep(6)

        # 等待ProseMirror加载
        for i in range(10):
            pm_count = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
            if pm_count > 0:
                break
            print(f"  等待ProseMirror加载... ({i+1}/10)")
            time.sleep(1)
        
        pm_count = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
        print(f"  ProseMirror数量: {pm_count}")

        try:
            close_btn = page.ele('text:关闭', timeout=2)
            if close_btn:
                close_btn.click()
                time.sleep(1)
        except Exception:
            pass

        # 第1步：先填标题（不填正文，保持在页面顶部，封面区域可见）
        title_text = title[:30] if len(title) > 30 else title
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
            print(f"  标题已填写: {title_text}")

        # 第2步：上传封面图（在页面顶部，封面区域可见）
        if cover_files:
            upload_cover_images(page, cover_files)

        # 第3步：填正文
        if html_path and os.path.exists(html_path):
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
// 触发input和change事件通知React
editor.dispatchEvent(new Event('input', {{bubbles: true}}));
editor.dispatchEvent(new Event('change', {{bubbles: true}}));
return 'content_ok';
""")
                print(f"  正文已填写 ({result})")
                time.sleep(2)
                
                # 点击编辑器外部触发blur，确保字数统计更新
                page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.dispatchEvent(new Event('blur', {bubbles: true}));
}
// 点击标题区域触发focus切换
var title = document.querySelector('textarea[placeholder*="文章标题"]');
if (title) {
    title.focus();
    title.dispatchEvent(new Event('focus', {bubbles: true}));
    setTimeout(function() { title.blur(); }, 100);
}
""")
                time.sleep(1)
                
                total_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
                img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
                print(f"  正文: 约{total_chars}字, {img_count}张图片")

        time.sleep(1)

        # 保存草稿
        save_draft(page)

        time.sleep(2)

    page.quit()
    print("\n完成！")


if __name__ == "__main__":
    main()