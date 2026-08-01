# -*- coding: utf-8 -*-
"""上传9篇文章到头条号草稿箱（含正文图片，使用paste事件）"""
import os, json, time, sys, base64
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

def paste_image(page, img_path):
    """通过模拟paste事件将图片上传到编辑器"""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    js = f"""
    (async function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';

        const byteString = atob('{img_b64}');
        const ab = new ArrayBuffer(byteString.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < byteString.length; i++) {{
            ia[i] = byteString.charCodeAt(i);
        }}
        const blob = new Blob([ab], {{type: 'image/jpeg'}});
        const file = new File([blob], 'image.jpg', {{type: 'image/jpeg'}});
        const dt = new DataTransfer();
        dt.items.add(file);
        const pasteEvent = new ClipboardEvent('paste', {{
            bubbles: true, cancelable: true, clipboardData: dt
        }});
        editor.focus();
        editor.dispatchEvent(pasteEvent);
        return 'ok';
    }})()
    """
    return page.run_js(js)

def move_cursor_to_para(page, para_index):
    """将光标移到指定段落后"""
    js = f"""
    const editor = document.querySelector('.ProseMirror');
    const paras = editor.querySelectorAll('p');
    if (paras.length >= {para_index}) {{
        const target = paras[{para_index - 1}];
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
    return page.run_js(js)

log("=" * 50)
log("上传9篇文章（含正文图片）")
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

        # 将文章分段
        paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
        valid_covers = [cf for cf in cover_files[:3] if os.path.exists(cf)]
        para_count = len(paragraphs)

        # 构建正文（文本部分）
        html_parts = "".join(f"<p>{p}</p>" for p in paragraphs)
        js = f"""
        const editor = document.querySelector('.ProseMirror');
        editor.innerHTML = {json.dumps(html_parts)};
        editor.dispatchEvent(new Event('input', {{bubbles: true}}));
        """
        page.run_js(js)
        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
        log(f"  正文: 约{chars}字, {para_count}段")

        # 插入图片（在段落间）
        img_count = 0
        if valid_covers:
            # 布局: 第1段后1张，之后每2段1张
            positions = []
            if para_count >= 1:
                positions.append(1)  # 第1段后
            if para_count >= 3:
                positions.append(3)  # 第3段后
            if para_count >= 5:
                positions.append(5)  # 第5段后

            for ci, cf in enumerate(valid_covers):
                if ci >= len(positions):
                    break
                pos = positions[ci]

                log(f"    图片{ci+1}: 插入到第{pos}段后")
                # 移动光标
                move_cursor_to_para(page, pos)
                time.sleep(0.5)

                # 粘贴图片
                result = paste_image(page, cf)
                time.sleep(2)

                # 检查是否成功
                img_count_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
                if img_count_now and int(img_count_now) > img_count:
                    img_count = int(img_count_now)
                    log(f"      [OK] 已上传, 当前共{img_count}张图")
                else:
                    log(f"      [失败] result={result}")

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