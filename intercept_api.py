#!/usr/bin/env python3
"""拦截头条自动保存的网络请求，分析正确的API格式"""
import os, re, json, time, base64, asyncio, io, urllib.parse
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

# 保存拦截到的请求
captured_requests = []


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


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    art = articles[0]  # 只用第一篇测试
    title = art["title"]
    paragraphs, images = extract_html_text_and_images(art["html_file"])
    print(f"文章: {title}")
    print(f"段落: {len(paragraphs)}段, 图片: {len(images)}张")

    # 压缩图片
    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"压缩: {len(img_bytes_list)}张")

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

        # 拦截所有包含 "agw" 的请求
        async def handle_route(route):
            url = route.request.url
            if "agw" in url:
                method = route.request.method
                post_data = route.request.post_data
                headers = dict(route.request.headers)
                captured_requests.append({
                    "url": url,
                    "method": method,
                    "post_data": post_data,
                    "headers": {k: v for k, v in headers.items() if k.lower() in ['content-type', 'x-csrftoken', 'referer', 'origin']},
                    "time": time.time()
                })
                print(f"\n>>> INTERCEPT: {method} {url[:120]}")
                if post_data:
                    print(f"    POST data ({len(post_data)} bytes): {post_data[:500]}")
            await route.continue_()

        await page.route("**/*", handle_route)

        # 验证登录
        print("验证登录...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")

        # 导航到发布页面
        print("导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 移除遮罩层
        await page.evaluate("""
            () => {
                const masks = document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay');
                masks.forEach(m => m.remove());
                const drawers = document.querySelectorAll('.byte-drawer-wrapper');
                drawers.forEach(d => d.remove());
            }
        """)
        await asyncio.sleep(1)

        # 关闭弹窗
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
            print("[ERROR] 编辑器未就绪")
            await browser.close()
            return

        # 清空之前捕获的请求
        captured_requests.clear()

        # 步骤1: 填标题
        print("填写标题...")
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(3)
        print(f"  标题已填写: {title}")

        # 步骤2: 逐段输入文字（键盘输入）
        print("输入正文...")
        editor_el = page.locator('.ProseMirror').first
        await editor_el.click()
        await asyncio.sleep(0.5)

        for pi, para_text in enumerate(paragraphs):
            print(f"  段落{pi+1}/{len(paragraphs)} ({len(para_text)}字)...")
            await editor_el.click()
            await asyncio.sleep(0.2)
            await page.keyboard.type(para_text, delay=3)
            await asyncio.sleep(0.3)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.3)

        # 步骤3: 粘贴图片
        print("粘贴图片...")
        await editor_el.click()
        await asyncio.sleep(0.3)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.3)

        for img_idx, img_bytes in enumerate(img_bytes_list):
            print(f"  图片{img_idx+1}/{len(img_bytes_list)}...")
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
                    const file = new File([blob], 'img_{img_idx}.jpg', {{type: 'image/jpeg'}});
                    const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                    Object.defineProperty(ev, 'clipboardData', {{
                        value: {{files: [file], items: [], types: ['Files'],
                            getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}}
                    }});
                    ed.dispatchEvent(ev);
                }}
            """)
            await asyncio.sleep(2)
            await page.keyboard.press('Enter')
            await asyncio.sleep(1)

        # 步骤4: 等待自动保存
        print("\n等待自动保存 (30秒)...")
        for i in range(30):
            await asyncio.sleep(1)
            # 检查是否有新请求
            if captured_requests:
                print(f"  [{i+1}s] 已捕获 {len(captured_requests)} 个请求")
            # 检查保存提示
            saved = await page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1;
                }
            """)
            if saved:
                print(f"  [{i+1}s] 检测到保存提示!")
                break

        # 输出所有捕获的请求
        print(f"\n{'='*60}")
        print(f"捕获的请求 ({len(captured_requests)} 个):")
        for i, req in enumerate(captured_requests):
            print(f"\n--- 请求{i+1} ---")
            print(f"  URL: {req['url'][:200]}")
            print(f"  Method: {req['method']}")
            if req['post_data']:
                print(f"  Post data ({len(req['post_data'])} bytes):")
                # 尝试解析
                try:
                    parsed = urllib.parse.parse_qs(req['post_data'])
                    for k, v in parsed.items():
                        val = v[0]
                        if len(val) > 200:
                            val = val[:200] + f"...({len(val)} chars)"
                        print(f"    {k}: {val}")
                except:
                    print(f"    {req['post_data'][:500]}")
            print(f"  Headers: {req['headers']}")

        # 保存到文件
        with open("/workspace/captured_api.json", "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n已保存到 /workspace/captured_api.json")

        await page.screenshot(path="/workspace/intercept_test.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())