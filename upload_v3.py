#!/usr/bin/env python3
"""头条草稿箱上传 v3 - 浏览器内 fetch API 直调保存，绕过 ProseMirror

策略：
1. Playwright 打开发布页面
2. 逐张上传图片获取服务器URL
3. 通过 page.evaluate() 用 fetch 直接调用保存API
4. 验证草稿箱
"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"


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
    except Exception:
        return None


def calc_image_layout(total_paragraphs, num_images):
    if num_images <= 0 or total_paragraphs < 1:
        return {}
    if num_images == 1:
        return {1: 1}
    if num_images == 2:
        return {1: 1, total_paragraphs: 1} if total_paragraphs > 1 else {1: 2}
    if num_images == 3:
        return {1: 1, 3: 2} if total_paragraphs >= 4 else {1: 1, total_paragraphs: 2}
    if num_images == 4:
        return {1: 1, 3: 2, total_paragraphs: 1} if total_paragraphs >= 4 else {1: 1, 2: 2, total_paragraphs: 1}
    # 5张: 第1段后1张, 第3段后2张, 第5段后2张
    candidates = []
    for tail in [2, 3]:
        last = total_paragraphs - tail
        if last >= 5:
            gap = (last - 1) / 2
            pos = [1, int(round(1 + gap)), last]
            if pos[1] - pos[0] >= 2 and pos[2] - pos[1] >= 2:
                actual_tail = total_paragraphs - pos[2]
                candidates.append((max(pos[1]-pos[0]-1, pos[2]-pos[1]-1), actual_tail, pos))
    if not candidates:
        return {1: 1, 3: 2, 5: 2}
    candidates.sort(key=lambda x: (0 if x[0] <= 3 else 1, 0 if x[1] <= 2 else 1, x[0], x[1]))
    best = candidates[0][2]
    return {best[0]: 1, best[1]: 2, best[2]: 2}


async def upload_images_get_urls(page, img_bytes_list):
    """逐张上传图片，返回服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        # 清空编辑器
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = '<p></p>'; ed.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.3)

        # 粘贴图片
        b64 = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return;
                ed.focus();
                const b = "{b64}";
                const bs = atob(b);
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                Object.defineProperty(ev, 'clipboardData', {{
                    value: {{files: [file], items: [], types: ['Files'],
                        getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}}
                }});
                ed.dispatchEvent(ev);
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

        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            print(f"OK ({img_url[:50]}...)")
            image_urls.append(img_url)
        else:
            print(f"FAIL")
            image_urls.append("")
        await asyncio.sleep(0.5)
    return image_urls


async def get_pgc_id_from_page(page):
    """通过浏览器获取 pgc_id"""
    result = await page.evaluate("""
        async () => {
            try {
                const resp = await fetch(
                    'https://mp.toutiao.com/mp/agw/article/new?article_type=0&format=json&compat=1&column_no=',
                    { credentials: 'include' }
                );
                const data = await resp.json();
                return JSON.stringify(data);
            } catch(e) {
                return JSON.stringify({error: e.message});
            }
        }
    """)
    try:
        data = json.loads(result)
        pgc_id = data.get("data", {}).get("pgc_id", "")
        if pgc_id:
            return pgc_id
        # Try media_id
        media_id = data.get("data", {}).get("media", {}).get("id", "")
        return str(media_id) if media_id else ""
    except:
        return ""


async def save_via_fetch(page, pgc_id, title, content_html, word_count):
    """通过浏览器内 fetch 调用保存API - 使用安全参数传递"""
    result = await page.evaluate("""
        async ([pgcId, title, content, wordCount]) => {
            const extra = JSON.stringify({
                content_source: 100000000402,
                content_word_cnt: wordCount
            });
            
            const params = new URLSearchParams();
            params.append('article_type', '0');
            params.append('pgc_id', pgcId);
            params.append('source', '29');
            params.append('title', title);
            params.append('content', content);
            params.append('save', '0');
            params.append('entrance', 'main');
            params.append('timer_status', '0');
            params.append('timer_time', '');
            params.append('extra', extra);
            params.append('title_id', '');
            params.append('ic_uri_list', '[]');
            params.append('search_creation_info', '');
            params.append('is_refute_rumor', '0');
            params.append('appid_list', '[]');
            params.append('stock_ids', '[]');
            params.append('concern_list', '[]');
            params.append('comic_attr', '');
            params.append('is_app_preview', '');
            params.append('externalLinkChecked', 'false');
            params.append('externalLink', '');
            params.append('claimOrigin', '0');
            params.append('copyRightChecked', '1');
            params.append('subTitle', '');
            params.append('subCoverList', '[]');
            params.append('coverList', '[]');
            params.append('coverType', '0');
            params.append('articleAdType', '0');
            params.append('isFansArticle', '0');
            params.append('activityId', '');
            params.append('communitySync', '0');
            
            try {
                const resp = await fetch(
                    'https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Accept': 'application/json, text/plain, */*',
                        },
                        body: params.toString(),
                        credentials: 'include',
                    }
                );
                const data = await resp.json();
                return JSON.stringify(data);
            } catch(e) {
                return JSON.stringify({error: e.message});
            }
        }
    """, [pgc_id, title, content_html, word_count])
    try:
        return json.loads(result)
    except:
        return {"raw": result}


async def process_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
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
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except Exception:
        pass

    # 等待编辑器
    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except Exception:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 上传图片获取URL
    image_urls = []
    if img_bytes_list:
        print(f"  上传图片...")
        image_urls = await upload_images_get_urls(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    # 构建内容HTML
    valid_urls = [u for u in image_urls if u]
    image_layout = calc_image_layout(len(paragraphs), len(valid_urls))
    print(f"  图片布局: {image_layout}")

    content_parts = []
    img_idx = 0
    for para_idx, para_text in enumerate(paragraphs):
        content_parts.append(f"<p>{para_text}</p>")
        target_para = para_idx + 1
        if target_para in image_layout:
            for _ in range(image_layout[target_para]):
                if img_idx < len(valid_urls):
                    content_parts.append(f'<p><img src="{valid_urls[img_idx]}" alt=""></p>')
                    img_idx += 1

    content_html = "\n".join(content_parts)
    word_count = sum(len(p) for p in paragraphs)
    print(f"  内容: {word_count}字, {len(content_html)}字符")

    # 获取 pgc_id
    print(f"  获取pgc_id...")
    pgc_id = await get_pgc_id_from_page(page)
    if not pgc_id:
        print(f"  [ERROR] 无法获取pgc_id")
        return False
    print(f"  pgc_id: {pgc_id}")

    # 通过浏览器内 fetch 保存
    print(f"  调用保存API...")
    result = await save_via_fetch(page, pgc_id, title, content_html, word_count)
    if isinstance(result, dict):
        code = result.get('code', -1)
        msg = result.get('message', '')
        if code == 0 or msg == 'success':
            print(f"  [SUCCESS] 保存成功! pgc_id={result.get('data', {}).get('pgc_id', pgc_id)}")
            return True
        else:
            print(f"  [FAIL] code={code}, msg={msg}")
            # 尝试不带 pgc_id
            print(f"  尝试备用API (pgc_id='')...")
            result2 = await save_via_fetch(page, "", title, content_html, word_count)
            if isinstance(result2, dict):
                code2 = result2.get('code', -1)
                print(f"  备用: code={code2}, msg={result2.get('message', '')}")
    else:
        print(f"  [FAIL] 异常: {result}")
    return False


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    print(f"Chrome: {CHROME_PATH}")

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
        print("验证登录...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期，需要重新登录")
            await browser.close()
            return
        print("[OK] 登录有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await process_article(page, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        # 最终验证
        print(f"\n{'='*60}")
        print(f"验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        for art in articles:
            t = art["title"][:6]
            found = t in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_v3_final.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())