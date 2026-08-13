#!/usr/bin/env python3
"""组合方案：Playwright上传图片获取URL，API保存草稿"""
import os, re, json, time, base64, asyncio, io, urllib.parse
import requests
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def load_cookies():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_html_text_and_images(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
    for m in re.finditer(r'<p>([^<]+)</p>', html):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', html):
        images.append(m.group(1))
    return paragraphs, images

def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except:
        return None

async def upload_images_via_browser(page, img_bytes_list):
    """通过浏览器上传图片，返回服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        # 清空编辑器
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.innerHTML = '<p></p>';
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.3)

        # 上传图片
        b64_str = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                const b = "{b64_str}";
                const bs = atob(b);
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img_{img_idx}.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                const fd = {{files: [file], items: [], types: ['Files'],
                    getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                editor.dispatchEvent(ev);
            }}
        """)

        # 等待服务器URL
        img_url = ""
        for _ in range(60):
            await asyncio.sleep(1)
            img_url = await page.evaluate("""
                () => {
                    const img = document.querySelector('.ProseMirror img');
                    return img ? img.src : '';
                }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break
        image_urls.append(img_url)
        print(f"    图片{img_idx+1}: {'OK' if img_url else 'FAIL'}")
        await asyncio.sleep(1)
    return image_urls

def save_draft_via_api(session, pgc_id, title, content_html, word_count):
    """通过API保存草稿"""
    api_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231"

    extra = json.dumps({
        "content_source": 100000000402,
        "content_word_cnt": word_count,
    })

    form_data = {
        "article_type": "0",
        "pgc_id": pgc_id,
        "source": "29",
        "title": title,
        "content": content_html,
        "save": "0",
        "entrance": "main",
        "timer_status": "0",
        "timer_time": "",
        "extra": extra,
        "title_id": "",
        "ic_uri_list": "[]",
        "search_creation_info": "",
        "is_refute_rumor": "0",
        "appid_list": "[]",
        "stock_ids": "[]",
        "concern_list": "[]",
        "comic_attr": "",
        "is_app_preview": "",
        "externalLinkChecked": "false",
        "externalLink": "",
        "claimOrigin": "0",
        "copyRightChecked": "1",
        "subTitle": "",
        "subCoverList": "[]",
        "coverList": "[]",
        "coverType": "0",
        "articleAdType": "0",
        "isFansArticle": "0",
        "activityId": "",
        "communitySync": "0",
    }

    csrf = session.cookies.get('passport_csrf_token', '')
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if csrf:
        headers["X-CSRFToken"] = csrf

    try:
        resp = session.post(api_url, data=form_data, headers=headers, timeout=30)
        result = resp.json()
        if result.get('message') == 'success' or result.get('code') == 0:
            return True, result
        return False, result
    except Exception as e:
        return False, {"error": str(e)}

def get_new_pgc_id(session):
    """获取新建文章的pgc_id"""
    resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
        "article_type": 0, "format": "json", "compat": 1, "column_no": "",
    }, timeout=15)
    try:
        data = resp.json()
        pgc_id = data.get("data", {}).get("pgc_id", "")
        return pgc_id
    except:
        return ""

async def process_article(page, session, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n[{index}/{total}] {title}")

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 未提取到文字内容")
        return False

    # 压缩图片
    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张")

    # 导航到发布页面
    print(f"  导航到发布页面...")
    await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except:
        pass

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 上传图片获取URL
    image_urls = []
    if img_bytes_list:
        print(f"  上传{len(img_bytes_list)}张图片...")
        image_urls = await upload_images_via_browser(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    # 构建内容HTML（带图片URL）
    content_parts = []
    img_idx = 0
    n_imgs = len(image_urls)
    image_layout = {}
    if n_imgs >= 5:
        image_layout = {1: 1, 3: 2, 5: 2}
    elif n_imgs >= 3:
        image_layout = {1: 1, 3: 2}
    elif n_imgs >= 1:
        image_layout = {1: 1}

    for para_idx, para_text in enumerate(paragraphs):
        content_parts.append(f"<p>{para_text}</p>")
        target_para = para_idx + 1
        if target_para in image_layout:
            num_imgs = image_layout[target_para]
            for _ in range(num_imgs):
                if img_idx < n_imgs and image_urls[img_idx]:
                    content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt=""></p>')
                    img_idx += 1

    content_html = "\n".join(content_parts)
    word_count = sum(len(p) for p in paragraphs)

    # 获取pgc_id
    pgc_id = get_new_pgc_id(session)
    if not pgc_id:
        print("  [ERROR] 无法获取pgc_id")
        return False

    # 通过API保存草稿
    print(f"  API保存 (pgc_id={pgc_id}, {word_count}字, {len(content_html)}字符)...")
    ok, result = save_draft_via_api(session, pgc_id, title, content_html, word_count)
    if ok:
        print(f"  [SUCCESS] 草稿保存成功!")
        return True
    else:
        code = result.get('code', '?')
        msg = result.get('message', str(result))
        print(f"  [FAIL] 保存失败: code={code}, msg={msg}")
        return False

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    cookies = load_cookies()

    print(f"共 {len(articles)} 篇文章待上传到草稿箱")
    print("=" * 60)

    # 创建API session
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://mp.toutiao.com/",
        "Origin": "https://mp.toutiao.com",
    })
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".toutiao.com", path="/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA
        )
        cookie_list = [{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 验证登录
        print("验证登录状态...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录状态有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await process_article(page, session, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        await browser.close()

    # 验证草稿箱
    print(f"\n验证草稿箱...")
    resp = session.get("https://mp.toutiao.com/profile_v4/manage/draft", timeout=15)
    for art in articles:
        title = art["title"]
        if title[:8] in resp.text:
            print(f"  ✓ {title}")
        else:
            print(f"  ✗ {title}")

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇成功")

if __name__ == "__main__":
    asyncio.run(main())