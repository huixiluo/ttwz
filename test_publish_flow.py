#!/usr/bin/env python3
"""测试：只输入一篇文章，然后点击"预览并发布"看效果"""
import os, re, json, time, base64, asyncio, io
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

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    # 只测试第一篇文章
    art = articles[0]
    title = art["title"]
    html_path = art["html_file"]

    print(f"测试文章: {title}")

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"段落: {len(paragraphs)}段, 图片: {len(images)}张")

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

        # 监听网络请求，记录所有 publish 和 save 请求
        network_log = []
        async def on_request(request):
            if any(k in request.url for k in ['publish', 'save', 'draft', 'ugc']):
                network_log.append({
                    "type": "request",
                    "url": request.url[:200],
                    "method": request.method,
                    "post_data": (request.post_data or "")[:500]
                })
        async def on_response(response):
            if any(k in response.url for k in ['publish', 'save', 'draft', 'ugc']):
                try:
                    body = await response.text()
                except:
                    body = "[error]"
                network_log.append({
                    "type": "response",
                    "url": response.url[:200],
                    "status": response.status,
                    "body": body[:500]
                })
        page.on("request", on_request)
        page.on("response", on_response)

        # 导航到编辑器
        print("导航到编辑器...")
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

        await page.wait_for_selector(".ProseMirror", timeout=15000)

        # 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            print(f"上传完成: {len([u for u in image_urls if u])}/{len(img_bytes_list)}张成功")

        valid_urls = [u for u in image_urls if u]
        image_layout = {1: 1, 3: 2, 5: 2}

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

        # 逐段输入
        print(f"逐段输入内容 ({len(paragraphs)}段)...")
        img_idx = 0
        for pi, para_text in enumerate(paragraphs):
            print(f"  段落{pi+1}/{len(paragraphs)}...")
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
        print(f"填写标题...")
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

        # 截图
        await page.screenshot(path="/workspace/before_publish.png")
        print("截图: /workspace/before_publish.png")

        # === 点击"预览并发布" ===
        print("\n点击'预览并发布'...")
        try:
            publish_btn = page.locator("button:has-text('预览并发布')").first
            await publish_btn.click()
            print("已点击，等待跳转...")
            await asyncio.sleep(5)

            current_url = page.url
            print(f"当前URL: {current_url[:200]}")
            await page.screenshot(path="/workspace/after_publish_click.png")

            # 检查是否有确认弹窗
            body_text = await page.evaluate("() => document.body.innerText.substring(0, 1000)")
            print(f"页面内容:\n{body_text[:500]}")

            # 如果还在当前页，检查是否有弹窗
            # 尝试找"确认发布"、"发布"等按钮
            for btn_text in ["确认发布", "发布", "确定", "取消"]:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if await btn.is_visible(timeout=2000):
                    print(f"  发现按钮: '{btn_text}'")
                    if btn_text in ["取消", "关闭"]:
                        await btn.click()
                        print(f"  点击了'{btn_text}'取消发布")
                        await asyncio.sleep(2)

        except Exception as e:
            print(f"错误: {e}")

        # 打印网络日志
        print(f"\n=== 网络请求日志 ({len(network_log)}条) ===")
        for entry in network_log[-20:]:
            print(f"  [{entry['type']}] {entry.get('method','')} {entry['url'][:120]}")
            if entry['type'] == 'response':
                print(f"    status={entry['status']} body={entry['body'][:200]}")

        # 检查草稿箱
        print(f"\n=== 检查草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        found = title[:6] in draft_content
        print(f"  {'[OK] 找到!' if found else '[MISS] 未找到'} {title}")
        await page.screenshot(path="/workspace/draft_box_after.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())