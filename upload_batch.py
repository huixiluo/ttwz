#!/usr/bin/env python3
"""批量上传文章到头条草稿箱 - 浏览器自动化方案"""
import os, re, json, time, base64, asyncio, io
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
        print(f"    上传图片{img_idx+1}/{len(img_bytes_list)}...")
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
        print(f"      {'OK' if img_url else 'FAIL'}")
        await asyncio.sleep(1)
    return image_urls

async def process_article(page, art, index, total):
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

    # 组合内容通过ProseMirror view.dispatch()设置
    # 构建内容节点
    content_nodes = []
    img_idx = 0
    n_imgs = len([u for u in image_urls if u])
    valid_urls = [u for u in image_urls if u]

    # 计算图片布局
    total_paras = len(paragraphs)
    image_layout = {}
    if n_imgs >= 5:
        image_layout = {1: 1, 3: 2, 5: 2}
    elif n_imgs >= 3:
        image_layout = {1: 1, 3: 2}
    elif n_imgs >= 1:
        image_layout = {1: 1}

    for para_idx, para_text in enumerate(paragraphs):
        content_nodes.append({"type": "paragraph", "content": [{"type": "text", "text": para_text}]})
        target_para = para_idx + 1
        if target_para in image_layout:
            num = image_layout[target_para]
            for _ in range(num):
                if img_idx < len(valid_urls):
                    img_url = valid_urls[img_idx]
                    content_nodes.append({
                        "type": "image",
                        "attrs": {"data": {"url": img_url, "icUri": img_url, "caption": ""}}
                    })
                    img_idx += 1

    # 通过ProseMirror view.dispatch()一次性设置完整内容
    print(f"  设置ProseMirror内容 ({len(content_nodes)}个节点)...")
    content_json = json.dumps(content_nodes, ensure_ascii=False)

    result = await page.evaluate(f"""
        () => {{
            function findView() {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return null;
                let desc = editor.pmViewDesc;
                while (desc) {{
                    if (desc.view && desc.view.state) return desc.view;
                    desc = desc.parent;
                }}
                // React Fiber fallback
                const fiberKey = Object.keys(editor).find(k => k.startsWith('__reactFiber'));
                if (fiberKey) {{
                    let fiber = editor[fiberKey];
                    for (let i = 0; i < 20 && fiber; i++) {{
                        if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) {{
                            return fiber.stateNode.view;
                        }}
                        fiber = fiber.return || fiber._owner;
                    }}
                }}
                return null;
            }}
            const view = findView();
            if (!view) return JSON.stringify({{status: 'no_view'}});
            const schema = view.state.schema;
            const nodes = {content_json};
            const docNodes = [];
            for (const n of nodes) {{
                if (n.type === 'paragraph') {{
                    docNodes.push(schema.node(schema.nodes.paragraph, null, n.content));
                }} else if (n.type === 'image') {{
                    docNodes.push(schema.node(schema.nodes.image, n.attrs));
                }}
            }}
            if (docNodes.length === 0) return JSON.stringify({{status: 'empty'}});
            const doc = schema.node(schema.nodes.doc, null, docNodes);
            view.dispatch(view.state.tr.replaceWith(0, view.state.doc.content.size, doc.content));
            return JSON.stringify({{status: 'ok', nodes: docNodes.length}});
        }}
    """)
    print(f"  ProseMirror: {result}")

    # 填写标题
    print(f"  填写标题...")
    await page.evaluate(f"""
        () => {{
            const ta = document.querySelector('textarea[placeholder*="标题"]');
            if (!ta) return 'no_title_area';
            const nativeSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
            nativeSetter.call(ta, '{title}');
            ta.dispatchEvent(new Event('input', {{bubbles: true}}));
            ta.dispatchEvent(new Event('change', {{bubbles: true}}));
            return 'ok';
        }}
    """)
    await asyncio.sleep(2)

    # 触发保存 - 点击保存按钮或等待自动保存
    print(f"  触发保存...")
    try:
        # 方法1: 点击"保存"按钮
        save_btn = page.locator('button:has-text("保存"), button:has-text("草稿"), span:has-text("保存"), span:has-text("草稿")').first
        if await save_btn.is_visible(timeout=3000):
            await save_btn.click()
            print(f"    点击保存按钮")
            await asyncio.sleep(3)
        else:
            # 方法2: 触发自动保存
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                        editor.dispatchEvent(new Event('blur', {bubbles: true}));
                    }
                }
            """)
            await asyncio.sleep(5)
    except:
        pass

    # 检查保存状态
    result = await page.evaluate("""
        () => {
            // 检查是否有保存成功提示
            const tips = document.querySelectorAll('[class*="save"], [class*="success"], [class*="toast"], [class*="message"]');
            const texts = [];
            for (const t of tips) {
                const txt = t.textContent?.trim();
                if (txt && (txt.includes('保存') || txt.includes('成功') || txt.includes('草稿'))) {
                    texts.push(txt);
                }
            }
            return JSON.stringify({texts: texts.slice(0, 3)});
        }
    """)
    print(f"  保存反馈: {result}")

    return True

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    cookies = load_cookies()

    print(f"共 {len(articles)} 篇文章待上传到草稿箱")
    print("=" * 60)

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
                ok = await process_article(page, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(3)

        await browser.close()

    # 验证草稿箱
    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")
    print(f"\n草稿箱地址: https://mp.toutiao.com/profile_v4/manage/draft")

if __name__ == "__main__":
    asyncio.run(main())