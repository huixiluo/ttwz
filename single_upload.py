# -*- coding: utf-8 -*-
"""修复版：单篇文章上传（修复图片位置+封面图上传）"""
import os, sys, json, time, base64
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

sys.path.insert(0, BASE_DIR)
import hot_news_writer as hnw

def log(msg):
    print(msg, flush=True)

def paste_image_at_cursor(page, img_b64):
    """在光标位置粘贴图片（不调用focus避免重置光标）"""
    js = f"""
    (async function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';

        const byteString = atob('{img_b64}');
        const ab = new ArrayBuffer(byteString.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
        const blob = new Blob([ab], {{type: 'image/jpeg'}});
        const file = new File([blob], 'image.jpg', {{type: 'image/jpeg'}});
        const dt = new DataTransfer();
        dt.items.add(file);
        const pasteEvent = new ClipboardEvent('paste', {{
            bubbles: true, cancelable: true, clipboardData: dt
        }});
        editor.dispatchEvent(pasteEvent);
        return 'ok';
    }})()
    """
    return page.run_js(js)

def move_cursor_after_para(page, para_index):
    """将光标移到指定<p>段落后（通过文本内容定位，避免索引偏移）"""
    js = f"""
    (function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';

        // 直接查找第N个p元素
        const paras = editor.querySelectorAll(':scope > p');
        if (paras.length < {para_index}) return 'out of range: ' + paras.length;

        const target = paras[{para_index - 1}];
        const range = document.createRange();
        range.setStartAfter(target);
        range.collapse(true);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        return 'ok';
    }})()
    """
    return page.run_js(js)

def upload_cover_images(page, cover_paths):
    """上传封面图（三图模式）"""
    if not cover_paths:
        return False

    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        return False

    log(f"  封面图: {len(valid)}张")

    # 查找封面区域
    try:
        # 点击三图模式
        three_img = page.ele('text:三图', timeout=3)
        if three_img:
            three_img.click()
            time.sleep(1)
            log("  已选择三图模式")

        # 尝试多种方式上传封面
        for ci, cf in enumerate(valid):
            success = False

            # 方法1: 查找封面上传的file input
            file_inputs = page.eles('tag:input@type=file')
            for fi in file_inputs:
                try:
                    if fi.attr('accept') and 'image' in (fi.attr('accept') or ''):
                        fi.input(cf)
                        time.sleep(2)
                        success = True
                        log(f"    封面{ci+1}: {os.path.basename(cf)}")
                        break
                except:
                    pass

            # 方法2: 点击封面区域的+号或上传按钮
            if not success:
                cover_btns = page.eles('text:上传', timeout=2) or page.eles('text:点击上传', timeout=2)
                for btn in cover_btns:
                    try:
                        btn.click()
                        time.sleep(1)
                        file_input = page.ele('tag:input@type=file', timeout=3)
                        if file_input:
                            file_input.input(cf)
                            time.sleep(2)
                            success = True
                            log(f"    封面{ci+1}: {os.path.basename(cf)}")
                            break
                    except:
                        pass

            if not success:
                log(f"    封面{ci+1}: 上传失败，需手动添加")

        return True
    except Exception as e:
        log(f"  封面上传异常: {e}")
        return False

# ===== 主流程 =====
log("=" * 50)
log("获取热搜 -> 生成文章 -> 上传草稿箱")
log("=" * 50)

config = hnw.load_config()
api_key = config["api_key"]
model = config.get("model", "deepseek-chat")
api_url = config.get("api_url", "https://api.deepseek.com/v1/chat/completions")

# 1. 获取热搜
log("\n[1] 获取微博娱乐热搜...")
session = hnw.get_visitor_session()
hot_list = hnw.get_hotsearch_list(session)
entertainment = [h for h in hot_list if hnw.classify_hot(h) == "娱乐"]
entertainment.sort(key=lambda x: x.get("rank", 999))

if not entertainment:
    log("没有娱乐类热搜")
    sys.exit(1)

hot = entertainment[0]
keyword = hot["word"]
log(f"选中: {hot['title']} (排名{hot['rank']})")

# 2. 生成文章
log("\n[2] DeepSeek改写...")
title, article = hnw.rewrite_article(keyword, hot["rank"], api_key, model, api_url)
log(f"标题: {title} ({len(title)}字)")
log(f"正文: {len(article)}字")

# 3. 获取配图
log("\n[3] 获取配图...")
images = hnw.fetch_images_baidu(keyword, count=5)
log(f"配图: {len(images)}张")

# 保存封面图
cover_dir = os.path.join(BASE_DIR, "output", "covers")
os.makedirs(cover_dir, exist_ok=True)
cover_paths = []
for i, b64 in enumerate(images[:3]):
    img_bytes = base64.b64decode(b64)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(cover_dir, f"single_{ts}_cover_{i+1}.jpg")
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    cover_paths.append(filepath)

# 4. 上传到头条号
log("\n[4] 上传到头条号草稿箱...")

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

# 打开发布页
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
title_el.clear()
title_el.input(title[:30])
log(f"标题: {title[:30]}")

# 上传封面图
upload_cover_images(page, cover_paths)

# 填正文
editor = page.ele('.ProseMirror', timeout=5)
editor.click()
time.sleep(1)

paragraphs = [p.strip() for p in article.split("\n") if p.strip()]
html_parts = "".join(f"<p>{p}</p>" for p in paragraphs)
page.run_js(f"""
const editor = document.querySelector('.ProseMirror');
editor.innerHTML = {json.dumps(html_parts)};
editor.dispatchEvent(new Event('input', {{bubbles: true}}));
""")
log(f"正文: {len(article)}字, {len(paragraphs)}段")

# 插入图片：第1段后1张, 第3段后2张, 第5段后2张
img_idx = 0
layout = [(1, 1), (3, 2), (5, 2)]

for pos, count in layout:
    if img_idx >= len(images):
        break

    # 移动光标到目标段落后
    ret = move_cursor_after_para(page, pos)
    log(f"  光标移到第{pos}段后: {ret}")
    time.sleep(0.5)

    for _ in range(count):
        if img_idx >= len(images):
            break
        log(f"    粘贴图片{img_idx+1}/{len(images)}")
        paste_image_at_cursor(page, images[img_idx])
        img_idx += 1
        time.sleep(2)

# 验证图片分布
img_info = page.run_js("""
const editor = document.querySelector('.ProseMirror');
const children = editor.children;
let result = [];
for (let i = 0; i < children.length; i++) {
    const c = children[i];
    if (c.tagName === 'P') {
        result.push('P:' + c.innerText.substring(0, 30));
    } else if (c.tagName === 'DIV') {
        result.push('IMG_WRAPPER');
    } else {
        result.push(c.tagName);
    }
}
return JSON.stringify(result);
""")
log(f"  元素分布: {img_info}")

# 等待保存
time.sleep(5)
save_tip = page.ele('text:已保存', timeout=3) or page.ele('text:保存成功', timeout=3)
log(f"保存: {'[OK]' if save_tip else '[提示] 应自动保存'}")

page.quit()

log(f"\n{'='*50}")
log("完成！")
log(f"标题: {title}")
log(f"热搜: {keyword}")
log(f"封面图: {len(cover_paths)}张")
log(f"正文配图: {img_idx}张")
log(f"{'='*50}")