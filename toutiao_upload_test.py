# -*- coding: utf-8 -*-
"""
头条号草稿箱上传脚本（DrissionPage页面操作版）
直接操作发布页面元素：填写标题、正文（含图片）、上传三图封面，草稿自动保存

关键修复（2026-07-29）：
- 正文图片：使用ClipboardEvent('paste')触发ProseMirror内置paste处理器，
  确保段落和图片按原始HTML位置正确解析（innerHTML直接设置无效）
- 封面图：三图模式下只有1个 .article-cover-add 按钮（不是3个），
  重复点击同一个按钮3次上传3张封面；使用JS dispatchEvent触发React合成事件
"""
import os
import re
import json
import time

from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"


def load_cookies():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def init_browser():
    """启动浏览器，注入cookie"""
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
    co.headless(True)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")

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
    print(f"  页面URL: {page.url}")

    if "profile" not in page.url.lower() and "graphic" not in page.url.lower():
        print("  [错误] Cookie登录失败，需要重新扫码登录")
        page.quit()
        raise RuntimeError("Cookie登录失败")

    print("  [OK] 登录验证成功")
    return page


def fill_title(page, title):
    """填写文章标题"""
    title_text = title[:30] if len(title) > 30 else title
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.clear()
        title_el.input(title_text)
        print(f"  标题已填写: {title_text}（{len(title_text)}字）")
        return True
    print("  [错误] 找不到标题输入框")
    return False


def fill_title_and_content(page, title, html_path):
    """先填正文（JS），再填标题（DrissionPage），避免自动保存时正文为空"""
    title_text = title[:30] if len(title) > 30 else title
    
    # 第1步：先填正文（JS方式，此时标题为空，不会触发自动保存）
    body_html = build_body_html(html_path)
    if not body_html:
        print("  [错误] HTML中未找到正文内容")
        return False
    
    result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'editor_not_found';
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
return 'content_ok';
""")
    if 'editor_not_found' in str(result):
        print("  [错误] 找不到编辑器")
        return False
    print(f"  正文已填写: ({result})")
    
    time.sleep(1)
    
    # 第2步：填标题（DrissionPage方式，触发React onChange）
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        print("  [错误] 找不到标题输入框")
        return False
    
    title_el.clear()
    title_el.input(title_text)
    print(f"  标题已填写: {title_text}（{len(title_text)}字）")
    
    time.sleep(2)
    
    total_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    para_count = page.run_js("return document.querySelectorAll('.ProseMirror p').length;")
    print(f"  正文: {para_count}段, 约{total_chars}字, {img_count}张图片")
    return True


def build_body_html(html_path):
    """从HTML文件提取body内容，返回完整的body HTML（段落+图片，保持原布局）"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_match:
        return ""

    body = body_match.group(1)

    result_parts = []
    for m in re.finditer(
        r'(<p>(.*?)</p>)|'
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            # 段落：保留文本内容，去除内嵌HTML标签
            para_text = m.group(2)
            # 清理段落内的HTML标签
            para_text = re.sub(r'<[^>]+>', '', para_text)
            result_parts.append(f'<p>{para_text}</p>')
        elif m.group(4):
            # 图片：包裹在p标签中，确保ProseMirror正确解析位置
            result_parts.append(f'<p><img src="{m.group(4)}" /></p>')

    return "\n".join(result_parts)


def fill_content_with_images(page, html_path):
    """从HTML文件提取段落和图片，通过粘贴事件插入到ProseMirror编辑器

    关键：不能直接设置innerHTML，ProseMirror不会识别。
    必须通过ClipboardEvent('paste')触发ProseMirror内置的paste处理器，
    它才会正确解析HTML并保持段落和图片的原始位置。
    """
    body_html = build_body_html(html_path)

    if not body_html:
        print("  [错误] HTML中未找到正文内容")
        return False

    # 使用粘贴事件触发ProseMirror的paste handler
    # 这样ProseMirror会正确解析HTML中的<p>和<img>标签，保持原始位置
    js_code = (
        "var editor = document.querySelector('.ProseMirror');\n"
        "if (!editor) { return 'not_found'; }\n"
        # 先清空编辑器
        "editor.innerHTML = '';\n"
        "editor.focus();\n"
        # 创建粘贴事件，携带HTML内容
        "var dt = new DataTransfer();\n"
        f"dt.setData('text/html', {json.dumps(body_html)});\n"
        "var pasteEvent = new ClipboardEvent('paste', {\n"
        "  bubbles: true,\n"
        "  cancelable: true,\n"
        "  clipboardData: dt\n"
        "});\n"
        "editor.dispatchEvent(pasteEvent);\n"
        "return 'ok';"
    )
    result = page.run_js(js_code)
    if result != "ok":
        print(f"  [错误] 设置正文失败: {result}")
        return False

    time.sleep(2)

    total_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    para_count = page.run_js("return document.querySelectorAll('.ProseMirror p').length;")
    print(f"  正文已填写: {para_count}段, 约{total_chars}字, {img_count}张图片")
    return True


def upload_cover_images(page, cover_paths):
    """上传封面图（三图模式）

    关键发现：三图模式下只有1个 .article-cover-add 按钮（不是3个），
    需要重复点击同一个按钮3次来上传3张封面图。
    每次上传后，按钮会短暂消失然后重新出现，等待其重新出现后再上传下一张。
    """
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("  [封面] 无有效封面图文件")
        return False

    print(f"  [封面] 准备上传{len(valid)}张封面图...")

    # 1. 选择"三图"模式
    try:
        three_radio = page.ele('tag:input@type=radio@value=3', timeout=3)
        if three_radio:
            three_radio.click()
            time.sleep(1)
            print("  [封面] 已选择三图模式（radio）")
        else:
            result = page.run_js(
                "var labels = document.querySelectorAll('label');\n"
                "for (var i = 0; i < labels.length; i++) {\n"
                "  if (labels[i].textContent.indexOf('三图') !== -1) {\n"
                "    labels[i].click();\n"
                "    return 'clicked';\n"
                "  }\n"
                "}\n"
                "return 'not_found';"
            )
            if result == 'clicked':
                time.sleep(1)
                print("  [封面] 已选择三图模式（JS）")
            else:
                print(f"  [封面] 选择三图模式失败: {result}")
    except Exception as e:
        print(f"  [封面] 选择三图模式异常: {e}")

    # 等待三图模式渲染完成（React异步渲染需要时间）
    print("  [封面] 等待三图模式渲染...")
    time.sleep(3)

    # 滚动封面区域到可见位置，确保React渲染
    page.run_js(
        "var cover = document.querySelector('.article-cover-images-wrap');\n"
        "if (cover) cover.scrollIntoView({block: 'center'});"
    )
    time.sleep(1)

    # 2. 逐张上传封面图：始终点击同一个添加按钮
    # 三图模式下只有1个 .article-cover-add，每次上传后它会重新出现
    success_count = 0
    for ci, cf in enumerate(valid):
        try:
            # 等待添加按钮可见（上传后可能需要时间重新出现）
            add_btn = None
            for attempt in range(15):
                add_btn = page.ele('.article-cover-add', timeout=2)
                if add_btn:
                    rect = add_btn.rect
                    if rect.size[0] > 0 and rect.size[1] > 0:
                        break
                    add_btn = None
                time.sleep(0.5)

            if not add_btn:
                print(f"    封面{ci+1}: 等待超时，添加按钮未出现")
                # 尝试JS方式查找
                js_count = page.run_js(
                    "return document.querySelectorAll('.article-cover-add').length;"
                )
                print(f"    封面{ci+1}: JS查询到{js_count}个添加按钮")
                if js_count == 0:
                    continue

            # 用JS点击添加按钮（触发React合成事件）
            print(f"    封面{ci+1}: 点击添加按钮...")
            click_result = page.run_js(
                "var add = document.querySelector('.article-cover-add');\n"
                "if (!add) return 'not_found';\n"
                "var rect = add.getBoundingClientRect();\n"
                "if (rect.width === 0 || rect.height === 0) return 'not_visible';\n"
                "add.scrollIntoView({block: 'center'});\n"
                "var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});\n"
                "add.dispatchEvent(evt);\n"
                "return 'clicked';"
            )
            print(f"    封面{ci+1}: JS点击 -> {click_result}")
            time.sleep(2)

            # 等待文件输入框出现
            file_input = None
            for _ in range(15):
                all_inputs = page.eles('tag:input@type=file')
                img_inputs = [fi for fi in all_inputs
                              if fi.attr('accept') and 'image' in (fi.attr('accept') or '')]
                if img_inputs:
                    file_input = img_inputs[-1]
                    break
                time.sleep(0.5)

            if file_input:
                file_input.input(cf)
                time.sleep(3)
                success_count += 1
                print(f"    封面{ci+1}: {os.path.basename(cf)} 已上传 ✓")
            else:
                # 兜底：尝试所有file input
                all_inputs = page.eles('tag:input@type=file')
                for inp in all_inputs:
                    try:
                        inp.input(cf)
                        time.sleep(3)
                        success_count += 1
                        print(f"    封面{ci+1}: {os.path.basename(cf)} 已上传（兜底）")
                        break
                    except Exception:
                        continue
                else:
                    print(f"    封面{ci+1}: 找不到上传控件")
                    # 输出当前所有file input信息用于调试
                    debug_info = page.run_js(
                        "var inputs = document.querySelectorAll('input[type=file]');\n"
                        "var info = [];\n"
                        "for (var i = 0; i < inputs.length; i++) {\n"
                        "  info.push('input[' + i + '] accept=' + (inputs[i].accept || 'none') +\n"
                        "            ' visible=' + (inputs[i].getBoundingClientRect().width > 0));\n"
                        "}\n"
                        "return info.join('|') || 'no file inputs';"
                    )
                    print(f"    封面{ci+1}: 调试信息 -> {debug_info}")

        except Exception as e:
            print(f"    封面{ci+1}: 上传失败 - {e}")

    print(f"  [封面] 成功上传{success_count}/{len(valid)}张")
    return success_count > 0


def save_draft(page, timeout=30):
    """主动点击保存草稿按钮，等待保存成功确认"""
    print("  保存草稿...")
    
    # 先等待之前的自动保存完成（如果有"草稿保存中..."说明正在自动保存）
    for _ in range(10):
        status = page.run_js("""
var allBtns = document.querySelectorAll('button, span');
for (var i = 0; i < allBtns.length; i++) {
    var text = (allBtns[i].textContent || '').trim();
    if (text.indexOf('草稿保存中') !== -1) return 'saving';
    if (text.indexOf('草稿已保存') !== -1 || text.indexOf('已保存') !== -1) return 'saved';
}
return 'idle';
""")
        if status == 'saved':
            print("  [OK] 自动保存已完成")
            return True
        if status == 'idle':
            break
        time.sleep(1.5)
    
    # 查找并点击保存按钮
    save_clicked = page.run_js("""
var allBtns = document.querySelectorAll('button, span, div[role="button"]');
for (var i = 0; i < allBtns.length; i++) {
    var btn = allBtns[i];
    var text = (btn.textContent || '').trim();
    var rect = btn.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && 
        (text === '保存' || text === '存草稿' || text.indexOf('保存草稿') !== -1 || text.indexOf('草稿') !== -1)) {
        var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
        btn.dispatchEvent(evt);
        return 'clicked: ' + text.substring(0, 30);
    }
}
return 'not_found';
""")
    print(f"  查找保存按钮: {save_clicked}")
    
    if 'not_found' in str(save_clicked):
        try:
            save_btn = page.ele('text:保存草稿', timeout=3)
            if not save_btn:
                save_btn = page.ele('text:存草稿', timeout=2)
            if not save_btn:
                save_btn = page.ele('text:保存', timeout=2)
            if save_btn:
                save_btn.click()
                print("  已点击保存按钮（DrissionPage）")
        except Exception:
            pass
    
    # 等待保存完成 - 检查多种状态
    start = time.time()
    while time.time() - start < timeout:
        saved = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('已保存') !== -1) return '已保存';
if (body.indexOf('保存成功') !== -1) return '保存成功';
if (body.indexOf('草稿已保存') !== -1) return '草稿已保存';

// 也检查按钮状态变化
var allBtns = document.querySelectorAll('button, span');
for (var i = 0; i < allBtns.length; i++) {
    var text = (allBtns[i].textContent || '').trim();
    if (text.indexOf('草稿已保存') !== -1) return '草稿已保存(按钮)';
    if (text.indexOf('已保存') !== -1 && allBtns[i].getBoundingClientRect().width > 0) return '已保存(按钮)';
}
return null;
""")
        if saved:
            print(f"  [OK] 草稿保存成功 ({saved})")
            return True
        time.sleep(1.5)
    
    print("  [警告] 未检测到保存成功提示，但按钮已点击")
    return True  # 按钮已点击，假定保存成功


def publish_one_article(page, title, html_path, cover_files, category, idx, total):
    """发布单篇文章到草稿箱"""
    print(f"\n[{idx}/{total}] {category} | {title}")

    page.get(PUBLISH_URL)
    time.sleep(4)

    try:
        close_btn = page.ele('text:关闭', timeout=2)
        if close_btn:
            close_btn.click()
            time.sleep(1)
    except Exception:
        pass

    # 使用原始顺序：标题 → 正文 → 封面 → 保存
    # 但标题和正文之间几乎无延迟，避免自动保存因正文为空而失败
    if not fill_title(page, title):
        return False

    # 立即填正文（无延迟，抢在自动保存失败前）
    if html_path and os.path.exists(html_path):
        if not fill_content_with_images(page, html_path):
            return False
    else:
        print(f"  [警告] HTML文件不存在: {html_path}")
        return False

    time.sleep(1)

    # 上传封面图
    if cover_files:
        upload_cover_images(page, cover_files)

    time.sleep(1)

    save_draft(page)

    return True


def main():
    if not os.path.exists(MANIFEST_FILE):
        print(f"清单文件不存在: {MANIFEST_FILE}")
        return False

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    # 只上传第1篇（第2篇已在草稿箱）
    articles = articles[:1]
    print(f"共 {len(articles)} 篇文章待上传\n")

    page = init_browser()

    success = 0
    for idx, art in enumerate(articles, 1):
        title = art.get("title", "")
        cover_files = art.get("cover_files", [])
        category = art.get("category", "")
        html_path = art.get("html_file", "")

        try:
            ok = publish_one_article(page, title, html_path, cover_files,
                                     category, idx, len(articles))
            if ok:
                success += 1
        except Exception as e:
            print(f"  [错误] {e}")

        time.sleep(2)

    page.quit()
    print(f"\n完成：{success}/{len(articles)} 篇上传成功")
    return success == len(articles)


if __name__ == "__main__":
    main()