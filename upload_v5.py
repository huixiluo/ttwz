#!/usr/bin/env python3
"""头条草稿箱上传 v5 - 捕获页面 msToken/a_bogus 后调用 API

策略：
1. 打开页面，填写标题触发自动保存
2. 拦截自动保存请求，捕获 msToken 和 a_bogus
3. 用捕获的 token 调用 API 保存完整内容
"""
import os, re, json, time, base64, asyncio, io
from urllib.parse import urlparse, parse_qs
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


class TokenCapture:
    def __init__(self):
        self.ms_token = ""
        self.a_bogus = ""
        self.captured = False

    async def handle_route(self, route):
        url = route.request.url
        if "article/publish" in url and not self.captured:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            self.ms_token = qs.get('msToken', [''])[0]
            self.a_bogus = qs.get('a_bogus', [''])[0]
            if self.ms_token:
                self.captured = True
                print(f"  [TOKEN] 捕获 msToken: {self.ms_token[:50]}...")
                print(f"  [TOKEN] 捕获 a_bogus: {self.a_bogus[:50]}...")
        await route.continue_()


async def upload_images_get_urls(page, img_bytes_list):
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = '<p></p>'; ed.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.3)

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

        img_url = ""
        for _ in range(60):
            await asyncio.sleep(1)
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break

        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            print(f"OK")
            image_urls.append(img_url)
        else:
            print(f"FAIL")
            image_urls.append("")
        await asyncio.sleep(0.5)
    return image_urls


async def capture_tokens_by_title(page, token_capture, title):
    """通过填写标题触发自动保存，从而捕获 token"""
    print(f"  填写标题触发自动保存...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click()
    await asyncio.sleep(0.5)
    await title_el.fill(title)
    await asyncio.sleep(3)
    
    # 等待捕获
    for _ in range(10):
        await asyncio.sleep(1)
        if token_capture.captured:
            return True
    return False


async def save_article(page, token_capture, title, content_html, word_count, image_urls, title_id):
    """用捕获的 token 调用 API"""
    covers_json = "[]"
    draft_form = json.dumps({"coverType": 2})
    
    extra = json.dumps({
        "content_source": 100000000402,
        "content_word_cnt": word_count,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
        "tuwen_wtt_transfer_switch": "1"
    })
    
    search_info = json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""})
    mp_editor_stat = json.dumps({"image": 1 if image_urls else 0})
    
    # 构建带 token 的 URL
    ms_token = token_capture.ms_token
    a_bogus = token_capture.a_bogus
    api_url = f"https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0&msToken={ms_token}&a_bogus={a_bogus}"
    
    result = await page.evaluate("""
        async ([apiUrl, title, content, extra, searchInfo, titleId, mpEditorStat, draftForm, coversJson]) => {
            const params = new URLSearchParams();
            params.append('source', '29');
            params.append('extra', extra);
            params.append('content', content);
            params.append('title', title);
            params.append('search_creation_info', searchInfo);
            params.append('title_id', titleId);
            params.append('mp_editor_stat', mpEditorStat);
            params.append('is_refute_rumor', '0');
            params.append('save', '0');
            params.append('entrance', '');
            params.append('timer_status', '0');
            params.append('timer_time', '');
            params.append('educluecard', '');
            params.append('draft_form_data', draftForm);
            params.append('pgc_feed_covers', coversJson);
            params.append('article_ad_type', '3');
            params.append('is_fans_article', '0');
            params.append('govern_forward', '0');
            params.append('praise', '0');
            params.append('disable_praise', '0');
            params.append('tree_plan_article', '0');
            params.append('star_order_id', '');
            params.append('star_order_name', '');
            params.append('customer_nick_name', '');
            params.append('activity_tag', '0');
            params.append('trends_writing_tag', '0');
            params.append('claim_exclusive', '1');
            
            try {
                const resp = await fetch(apiUrl, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'Accept': 'application/json, text/plain, */*'},
                    body: params.toString(),
                    credentials: 'include',
                });
                const data = await resp.json();
                return JSON.stringify(data);
            } catch(e) {
                return JSON.stringify({error: e.message});
            }
        }
    """, [api_url, title, content_html, extra, search_info, title_id, mp_editor_stat, draft_form, covers_json])
    try:
        return json.loads(result)
    except:
        return {"raw": result}


async def process_article(page, token_capture, art, index, total):
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

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张")

    print(f"  导航到发布页面...")
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 移除遮罩
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
            document.querySelectorAll('.byte-drawer-wrapper').forEach(d => d.remove());
        }
    """)
    await asyncio.sleep(1)

    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except Exception:
        pass

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except Exception:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 重置 token 捕获
    token_capture.captured = False
    token_capture.ms_token = ""
    token_capture.a_bogus = ""

    # 填写标题触发自动保存，捕获 token
    title_id = f"{int(time.time()*1000)}_1842848430550016"
    if not await capture_tokens_by_title(page, token_capture, title):
        print("  [WARN] 未能捕获 token，尝试无 token 调用")
    
    print(f"  title_id: {title_id}")

    # 上传图片
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
    track = 0
    for para_idx, para_text in enumerate(paragraphs):
        track += 1
        content_parts.append(f'<p data-track="{track}">{para_text}</p>')
        target_para = para_idx + 1
        if target_para in image_layout:
            for _ in range(image_layout[target_para]):
                if img_idx < len(valid_urls):
                    content_parts.append(f'<p class="pgc-p" data-track="{track+1}"><br></p>')
                    track += 1
                    content_parts.append(f'<p data-track="{track+1}"><img src="{valid_urls[img_idx]}" alt=""></p>')
                    track += 1
                    img_idx += 1

    content_html = "".join(content_parts)
    word_count = sum(len(p) for p in paragraphs)
    print(f"  内容: {word_count}字, {len(content_html)}字符")

    # 保存
    print(f"  调用保存API (msToken={'有' if token_capture.ms_token else '无'})...")
    result = await save_article(page, token_capture, title, content_html, word_count, valid_urls, title_id)
    if isinstance(result, dict):
        code = result.get('code', -1)
        msg = result.get('message', '')
        if code == 0 or msg == 'success':
            print(f"  [SUCCESS] 保存成功!")
            return True
        else:
            print(f"  [FAIL] code={code}, msg={msg}")
    else:
        print(f"  [FAIL] 异常: {result}")
    return False


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")

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

        # 设置 token 捕获
        token_capture = TokenCapture()
        await page.route("**/*", token_capture.handle_route)

        print("验证登录...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await process_article(page, token_capture, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        print(f"\n{'='*60}")
        print(f"验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        for art in articles:
            t = art["title"][:6]
            found = t in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_v5_final.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())