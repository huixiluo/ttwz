#!/usr/bin/env python3
"""上传 v7 - 键盘输入 → 提取ProseMirror HTML → API保存"""
import os, re, json, time, base64, asyncio, io, urllib.parse
import requests
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

async def upload_images_get_urls(page, img_bytes_list):
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
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
        print(f"      图片{img_idx+1}: {'OK' if img_url else 'FAIL'}")
        await asyncio.sleep(1)
    return image_urls

async def get_prosemirror_html(page):
    """获取ProseMirror编辑器的HTML内容"""
    html = await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return '';
            return editor.innerHTML;
        }
    """)
    return html

async def save_draft_api(session, pgc_id, title, content_html, word_count, ms_token, a_bogus):
    """通过API保存草稿，使用完整参数"""
    extra = json.dumps({
        "content_source": 100000000402,
        "content_word_cnt": word_count,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {
            "entrance": "",
            "from_page": "publisher_mp",
            "enter_from": "PC",
            "device_platform": "mp",
            "is_message": 0
        },
        "tuwen_wtt_transfer_switch": "1"
    })

    form_data = {
        "article_type": "0",
        "pgc_id": pgc_id,
        "source": "29",
        "title": title,
        "content": content_html,
        "extra": extra,
        "save": "0",
        "entrance": "main",
        "timer_status": "0",
        "timer_time": "",
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
    
    # 构建URL（包含msToken和a_bogus）
    params = {
        "source": "mp",
        "type": "article",
        "aid": "1231",
        "mp_publish_ab_val": "0",
    }
    if ms_token:
        params["msToken"] = ms_token
    # a_bogus需要特殊处理，可能包含特殊字符
    
    api_url = "https://mp.toutiao.com/mp/agw/article/publish"
    
    resp = session.post(api_url, params=params, data=form_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrf,
    })
    result = resp.json()
    return result

async def process_article(page, session, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n[{index}/{total}] {title}")

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 未提取到文字内容")
        return False

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张")

    # 导航到发布页面
    await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator("text=" + btn_text).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except:
        pass

    # 关闭"继续编辑"弹窗
    try:
        continue_btn = page.locator("button:has-text('继续编辑')").first
        if await continue_btn.is_visible(timeout=3000):
            await continue_btn.click()
            await asyncio.sleep(2)
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
        image_urls = await upload_images_get_urls(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    valid_urls = [u for u in image_urls if u]
    n_imgs = len(valid_urls)
    image_layout = {}
    if n_imgs >= 5:
        image_layout = {1: 1, 3: 2, 5: 2}
    elif n_imgs >= 3:
        image_layout = {1: 1, 3: 2}
    elif n_imgs >= 1:
        image_layout = {1: 1}

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

    editor_el = page.locator('.ProseMirror').first
    await editor_el.click()
    await asyncio.sleep(0.5)

    # 逐段输入 + 图片
    print(f"  逐段输入内容 ({len(paragraphs)}段)...")
    img_idx = 0
    for pi, para_text in enumerate(paragraphs):
        print(f"    段落{pi+1}/{len(paragraphs)} ({len(para_text)}字)...")
        await editor_el.click()
        await asyncio.sleep(0.2)
        await page.keyboard.type(para_text, delay=5)
        await asyncio.sleep(0.3)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.3)

        target_para = pi + 1
        if target_para in image_layout:
            num = image_layout[target_para]
            for _ in range(num):
                if img_idx < len(valid_urls):
                    img_url = valid_urls[img_idx]
                    print(f"      插入图片{img_idx+1}...")
                    await page.evaluate(f"""
                        () => {{
                            const editor = document.querySelector('.ProseMirror');
                            if (!editor) return;
                            editor.focus();
                            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                            const cd = {{
                                types: ['text/html'],
                                getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" />' : ''; }},
                                setData: function() {{}},
                                clearData: function() {{}},
                                files: [],
                                items: []
                            }};
                            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
                            editor.dispatchEvent(ev);
                        }}
                    """)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press('Enter')
                    await asyncio.sleep(0.3)
                    img_idx += 1

    # 填写标题
    print(f"  填写标题...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click()
    await asyncio.sleep(0.5)
    await title_el.fill(title)
    await asyncio.sleep(2)

    # 触发编辑器事件
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.dispatchEvent(new Event('input', {bubbles: true}));
                editor.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(3)

    # 获取ProseMirror的HTML内容
    prosemirror_html = await get_prosemirror_html(page)
    print(f"  ProseMirror HTML长度: {len(prosemirror_html)}")

    # 获取当前页面的pgc_id
    pgc_id = await page.evaluate("""
        () => {
            // 尝试从页面URL或状态中获取
            const url = window.location.href;
            const m = url.match(/pgc_id=(\\d+)/);
            if (m) return m[1];
            // 尝试从全局状态获取
            if (window.__INITIAL_STATE__) {
                const state = window.__INITIAL_STATE__;
                if (state.articlePgc && state.articlePgc.group_id) return String(state.articlePgc.group_id);
            }
            return '';
        }
    """)
    print(f"  页面pgc_id: {pgc_id}")

    # 获取msToken和a_bogus（从页面JS中提取）
    ms_token = await page.evaluate("""
        () => {
            // 尝试从window对象获取
            if (window.__MS_TOKEN__) return window.__MS_TOKEN__;
            return '';
        }
    """)

    # 使用ProseMirror HTML通过API保存
    word_count = sum(len(p) for p in paragraphs)
    
    if not pgc_id:
        # 获取新的pgc_id
        resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
            "article_type": 0, "format": "json", "compat": 1, "column_no": "",
        })
        try:
            data = resp.json()
            pgc_id = str(data.get("data", {}).get("media", {}).get("id", ""))
            print(f"  新pgc_id(from media.id): {pgc_id}")
        except:
            pass

    if not pgc_id:
        print("  [ERROR] 无法获取pgc_id")
        return False

    print(f"  API保存 (pgc_id={pgc_id}, {word_count}字, {n_imgs}图)...")
    result = await save_draft_api(session, pgc_id, title, prosemirror_html, word_count, ms_token, "")
    
    code = result.get('code', -1)
    msg = result.get('message', '')
    if code == 0:
        print(f"  [SUCCESS] 保存成功!")
        return True
    else:
        print(f"  [FAIL] code={code}, msg={msg}")
        # 打印部分响应
        print(f"  响应: {json.dumps(result, ensure_ascii=False)[:300]}")
        return False

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传到草稿箱")
    print("=" * 60)

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
            await asyncio.sleep(3)

        # 验证
        print(f"\n=== 验证草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        for art in articles:
            found = art["title"][:6] in draft_content
            print(f"  {'[OK]' if found else '[MISS]'} {art['title']}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")

if __name__ == "__main__":
    asyncio.run(main())