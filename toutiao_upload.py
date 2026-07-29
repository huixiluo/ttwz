# -*- coding: utf-8 -*-
"""
头条号草稿箱上传脚本（DrissionPage页面操作版）
直接操作发布页面元素：填写标题、正文、上传封面，草稿自动保存
"""
import os
import json
import time

from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = r"C:\Users\huixi\Documents\trae_projects\ttwz\output\batch_manifest.json"
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
        page.set.cookies({name: value, "domain": ".toutiao.com", "path": "/"})

    page.get(PUBLISH_URL)
    time.sleep(5)

    print(f"  页面标题: {page.title}")
    print(f"  页面URL: {page.url}")
    return page


def fill_title(page, title):
    """填写文章标题"""
    # 标题要求2~30字，头条号标题限制
    title_text = title[:30] if len(title) > 30 else title
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        # 尝试模糊匹配
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.clear()
        title_el.input(title_text)
        print(f"  标题已填写: {title_text}（{len(title_text)}字）")
        return True
    print("  [错误] 找不到标题输入框")
    return False


def fill_content(page, article_text, image_urls=None):
    """填写正文内容（ProseMirror编辑器）

    图片布局与生成HTML保持一致：
    - 第1段后插1张图
    - 之后每两段（第3、5、7...段后）插2张图
    图片以 <img> 形式插入段落之间。
    """
    paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
    image_urls = image_urls or []

    body_parts = []
    img_idx = 0

    def add_images(count):
        nonlocal img_idx
        for _ in range(count):
            if img_idx < len(image_urls):
                url = image_urls[img_idx]
                body_parts.append(
                    f'<p><img src="{url}" alt="" /></p>'
                )
                img_idx += 1

    for i, para in enumerate(paragraphs):
        body_parts.append(f"<p>{para}</p>")
        para_num = i + 1
        if para_num == 1:
            # 第一段后插1张图
            add_images(1)
        elif para_num % 2 == 1:
            # 之后每两段（第3、5、7...段后）插2张图
            add_images(2)

    html_parts = "".join(body_parts)

    # 用JS设置ProseMirror编辑器内容并触发input事件
    js_code = f"""
    const editor = document.querySelector('.ProseMirror');
    if (editor) {{
        editor.innerHTML = {json.dumps(html_parts)};
        editor.dispatchEvent(new Event('input', {{bubbles: true}}));
        editor.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'ok';
    }}
    return 'not_found';
    """
    result = page.run_js(js_code)
    if result == "ok":
        # 获取字数
        text = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
        print(f"  正文已填写: 约{text}字（含{img_idx}张配图）")
        return True
    print(f"  [错误] 找不到正文编辑器: {result}")
    return False


def upload_image_via_toolbar(page, image_path, timeout=20):
    """通过正文编辑器工具栏上传单张图片，返回上传后图片URL

    流程：点击工具栏图片按钮 → DrissionPage 处理文件选择 → 等待上传完成 → 读取最新img的src
    """
    # 记录上传前编辑器中已有图片数量，用于判断新图是否插入完成
    before_count = page.run_js(
        "return (document.querySelectorAll('.ProseMirror img') || []).length;"
    ) or 0

    # 查找工具栏图片按钮（多套选择器兜底）
    img_btn = (
        page.ele('tag:button@@text():图片', timeout=3) or
        page.ele('tag:span@@text():图片', timeout=2) or
        page.ele('@aria-label:插入图片', timeout=2) or
        page.ele('@title:图片', timeout=2) or
        page.ele('@class:image', timeout=2) or
        page.ele('@class:prose-image', timeout=2)
    )
    if not img_btn:
        print(f"  [正文图] 找不到工具栏图片按钮: {os.path.basename(image_path)}")
        return None

    img_btn.click()
    time.sleep(0.5)

    # DrissionPage 自动处理文件选择对话框
    page.upload(image_path)

    # 等待图片插入（图片数量增加视为成功）
    start = time.time()
    after_count = before_count
    while time.time() - start < timeout:
        time.sleep(1)
        after_count = page.run_js(
            "return (document.querySelectorAll('.ProseMirror img') || []).length;"
        ) or 0
        if after_count > before_count:
            break

    if after_count <= before_count:
        print(f"  [正文图] 上传超时未插入: {os.path.basename(image_path)}")
        return None

    # 读取最新插入图片的src
    url = page.run_js("""
        const imgs = document.querySelectorAll('.ProseMirror img');
        if (imgs.length === 0) return null;
        return imgs[imgs.length - 1].getAttribute('src') || imgs[imgs.length - 1].src;
    """)
    if url:
        print(f"  [正文图] 已上传: {os.path.basename(image_path)} -> {url[:60]}...")
    return url


def upload_cover(page, cover_files):
    """上传封面图
    头条号封面: 点击"展示封面"区域，选择"单图/三图"，上传图片
    """
    if not cover_files:
        return False

    # 查找封面上传区域
    # 页面有"展示封面"文字，附近有上传按钮
    cover_label = page.ele('text:展示封面', timeout=5)
    if not cover_label:
        print("  [封面] 找不到封面区域")
        return False

    # 尝试找到"三图"选项（支持3张封面）
    three_img_option = page.ele('text:三图', timeout=3)
    if three_img_option:
        three_img_option.click()
        time.sleep(1)
        print("  [封面] 已选择三图模式")

    # 查找上传按钮/区域（通常是"点击上传"或含upload的元素）
    upload_btn = page.ele('text:上传', timeout=3) or page.ele('text:点击上传', timeout=3)
    if not upload_btn:
        # 尝试找封面区域内的可点击元素
        upload_btn = page.ele('.article-cover-uploader', timeout=3) or \
                     page.ele('@class:cover', timeout=3)

    success_count = 0
    for cf in cover_files[:3]:
        if not os.path.exists(cf):
            print(f"  [封面] 文件不存在: {cf}")
            continue

        if upload_btn:
            upload_btn.click()
            time.sleep(0.5)

        # DrissionPage会自动处理文件选择对话框
        page.upload(cf)
        time.sleep(2)  # 等待上传完成
        success_count += 1
        print(f"  [封面] 已上传: {os.path.basename(cf)}")

    return success_count > 0


def wait_auto_save(page, timeout=15):
    """等待草稿自动保存"""
    print("  等待草稿自动保存...")
    start = time.time()
    while time.time() - start < timeout:
        # 检查是否有"已保存"或"保存成功"提示
        save_tip = page.ele('text:已保存', timeout=2) or \
                   page.ele('text:保存成功', timeout=2) or \
                   page.ele('text:草稿已保存', timeout=2)
        if save_tip:
            print(f"  [OK] 草稿已自动保存")
            return True
        time.sleep(2)

    # 即使没找到保存提示，内容可能已保存
    print(f"  [提示] 未检测到保存提示，内容可能已自动保存")
    return True


def upload_body_images(page, body_image_files):
    """依次上传正文配图，返回按上传顺序的图片URL列表

    上传时图片会被插入到编辑器末尾，因此需要先上传拿URL，
    再由 fill_content 统一重排正文HTML（按 1+2+2 布局插入）。
    """
    if not body_image_files:
        return []

    # 先把编辑器清空，避免已有内容干扰图片数量判断
    page.run_js("""
        const editor = document.querySelector('.ProseMirror');
        if (editor) {
            editor.innerHTML = '<p></p>';
            editor.dispatchEvent(new Event('input', {bubbles: true}));
        }
    """)
    time.sleep(0.5)

    urls = []
    for fp in body_image_files:
        if not os.path.exists(fp):
            print(f"  [正文图] 文件不存在: {fp}")
            urls.append(None)
            continue
        url = upload_image_via_toolbar(page, fp)
        urls.append(url)
        time.sleep(1)

    # 过滤掉上传失败的
    valid_urls = [u for u in urls if u]
    print(f"  [正文图] 共上传成功 {len(valid_urls)}/{len(body_image_files)} 张")
    return valid_urls


def publish_one_article(page, title, article, cover_files, body_image_files,
                        category, idx, total):
    """发布单篇文章到草稿箱

    流程：
    1. 打开发布页
    2. 填写标题
    3. 上传正文配图（拿到URL列表）
    4. 填写正文：按 1+2+2 布局把图片URL插入到段落之间
    5. 上传封面图（封面位三图）
    6. 等待草稿自动保存
    """
    print(f"\n[{idx}/{total}] {category} | {title}")

    # 访问发布页（每篇文章都需要新页面）
    page.get(PUBLISH_URL)
    time.sleep(4)

    # 填写标题
    if not fill_title(page, title):
        return False

    time.sleep(1)

    # 上传正文配图，拿到URL列表
    image_urls = []
    if body_image_files:
        image_urls = upload_body_images(page, body_image_files)

    time.sleep(1)

    # 填写正文（按 1+2+2 布局插入图片）
    if not fill_content(page, article, image_urls=image_urls):
        return False

    time.sleep(1)

    # 上传封面图
    if cover_files:
        upload_cover(page, cover_files)

    # 等待自动保存
    wait_auto_save(page)

    return True


def main():
    if not os.path.exists(MANIFEST_FILE):
        print(f"清单文件不存在: {MANIFEST_FILE}")
        return False

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传\n")

    page = init_browser()

    success = 0
    for idx, art in enumerate(articles, 1):
        title = art.get("title", "")
        article = art.get("article", "")
        cover_files = art.get("cover_files", [])
        body_image_files = art.get("body_images", [])
        category = art.get("category", "")

        try:
            ok = publish_one_article(page, title, article, cover_files,
                                     body_image_files, category, idx, len(articles))
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
