# -*- coding: utf-8 -*-
"""通过工具栏图片按钮上传文章内图片（使用实际的图片上传）"""
import os, json, time, sys
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

def upload_image_to_editor(page, img_path):
    """通过工具栏图片按钮上传图片到编辑器"""
    # 方法1: 查找.syl-toolbar-tool.image并点击
    img_btn = page.ele('.syl-toolbar-tool.image', timeout=3)
    if img_btn:
        page.set.upload_files(img_path)  # 预设上传文件
        img_btn.click()
        time.sleep(3)
        # 检查图片是否上传成功（编辑器里出现img标签）
        has_img = page.run_js("return document.querySelector('.ProseMirror img') !== null;")
        if has_img:
            return True

    # 方法2: 通过按钮索引点击
    btns = page.eles('.syl-toolbar-button')
    for bi in [0, 1, 2]:
        if bi >= len(btns):
            break
        page.set.upload_files(img_path)
        btns[bi].click()
        time.sleep(3)
        has_img = page.run_js("return document.querySelector('.ProseMirror img') !== null;")
        if has_img:
            return True

    # 方法3: 尝试查找所有可能的图片上传入口
    # 查找包含"图片"或"image"文本的元素
    for selector in ['text:图片', 'text:插入图片', 'text:上传图片', '.image-upload', '.insert-image']:
        el = page.ele(selector, timeout=2)
        if el:
            page.set.upload_files(img_path)
            el.click()
            time.sleep(3)
            has_img = page.run_js("return document.querySelector('.ProseMirror img') !== null;")
            if has_img:
                return True

    return False

log("=" * 50)
log("上传文章（含正文图片）")
log("=" * 50)

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    articles = json.load(f)

# 启动浏览器
co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

# 登录
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
page.get("https://mp.toutiao.com")
time.sleep(2)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)

if "profile" not in page.url.lower():
    log("登录失败")
    page.quit()
    sys.exit(1)

log("登录成功")

success = 0
for idx, art in enumerate(articles, 1):
    title = art.get("title", "")[:30]
    article_text = art.get("article", "")
    category = art.get("category", "")
    cover_files = art.get("cover_files", [])

    log(f"\n[{idx}/9] {category} | {title}")

    try:
        page.get(PUBLISH_URL)
        time.sleep(4)

        # 关闭弹窗
        try:
            close_btn = page.ele('text:关闭', timeout=2)
            if close_btn:
                close_btn.click()
                time.sleep(1)
        except:
            pass

        # 填标题
        title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
        if not title_el:
            log("  找不到标题输入框")
            continue
        title_el.clear()
        title_el.input(title)
        log(f"  标题: {title}")

        # 点击编辑器
        editor = page.ele('.ProseMirror', timeout=5)
        if not editor:
            log("  找不到编辑器")
            continue
        editor.click()
        time.sleep(1)

        # 将文章分段，在段落间插入图片占位符
        paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
        valid_covers = [cf for cf in cover_files[:3] if os.path.exists(cf)]

        # 构建HTML（先只放文本）
        html_parts = "".join(f"<p>{p}</p>" for p in paragraphs)
        js = f"""
        const editor = document.querySelector('.ProseMirror');
        if (editor) {{
            editor.innerHTML = {json.dumps(html_parts)};
            editor.dispatchEvent(new Event('input', {{bubbles: true}}));
            return 'ok';
        }}
        return 'not_found';
        """
        result = page.run_js(js)
        if result != "ok":
            log(f"  正文填写失败: {result}")
            continue
        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
        log(f"  正文: 约{chars}字")

        # 插入图片
        img_count = 0
        if valid_covers:
            para_count = page.run_js("return document.querySelectorAll('.ProseMirror > p').length;")
            log(f"  段落数: {para_count}, 图片数: {len(valid_covers)}")

            for ci, cf in enumerate(valid_covers):
                # 计算插入位置
                if ci == 0:
                    insert_pos = 1  # 第1段后
                else:
                    insert_pos = min(1 + ci * 2, para_count)

                # 将光标移到目标位置
                move_cursor_js = f"""
                const editor = document.querySelector('.ProseMirror');
                const paras = editor.querySelectorAll('p');
                if (paras.length >= {insert_pos}) {{
                    const target = paras[{insert_pos - 1}];
                    const range = document.createRange();
                    range.setStartAfter(target);
                    range.collapse(true);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    editor.focus();
                    return 'ok';
                }}
                return 'out of range';
                """
                page.run_js(move_cursor_js)
                time.sleep(0.5)

                # 尝试上传图片
                log(f"    图片{ci+1}: {os.path.basename(cf)}")
                if upload_image_to_editor(page, cf):
                    img_count += 1
                    log(f"      上传成功")
                else:
                    log(f"      上传失败")
                time.sleep(1.5)

            if img_count > 0:
                log(f"  共插入{img_count}张图片")

        # 等待保存
        time.sleep(5)
        save_tip = page.ele('text:已保存', timeout=3) or page.ele('text:保存成功', timeout=3)
        if save_tip:
            log("  [OK] 草稿已保存")
        else:
            log("  [提示] 内容已填写，应自动保存")

        success += 1
    except Exception as e:
        log(f"  [错误] {e}")
        import traceback
        traceback.print_exc()

    time.sleep(2)

log(f"\n{'='*50}")
log(f"完成: {success}/{len(articles)} 篇")
log(f"{'='*50}")
page.quit()