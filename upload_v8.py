#!/usr/bin/env python3
"""头条草稿箱上传 v8 - 每篇文章独立页面 + 增强遮罩处理 + 拦截API验证保存

核心改进：
1. 每篇文章用独立页面（避免前一篇的遮罩残留）
2. 更激进的遮罩层移除（循环检测+CSS隐藏+DOM移除）
3. 拦截自动保存API请求验证保存是否成功
4. 更长的等待时间，更完善的错误处理
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
    paragraphs, images = [], []
    for m in re.finditer(r'<p>([^<]+)</p>', html):
        text = m.group(1).strip()
        if text: paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', html):
        images.append(m.group(1))
    return paragraphs, images


def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        w, h = img.size
        if w > max_width: img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except: return None


def calc_image_layout(total_paragraphs, num_images):
    if num_images <= 0: return {}
    if num_images == 1: return {1: 1}
    if num_images == 2: return {1: 1, total_paragraphs: 1} if total_paragraphs > 1 else {1: 2}
    if num_images == 3: return {1: 1, 3: 2} if total_paragraphs >= 4 else {1: 1, total_paragraphs: 2}
    if num_images == 4: return {1: 1, 3: 2, total_paragraphs: 1} if total_paragraphs >= 4 else {1: 1, 2: 2, total_paragraphs: 1}
    candidates = []
    for tail in [2, 3]:
        last = total_paragraphs - tail
        if last >= 5:
            gap = (last - 1) / 2
            pos = [1, int(round(1 + gap)), last]
            if pos[1] - pos[0] >= 2 and pos[2] - pos[1] >= 2:
                candidates.append((max(pos[1]-pos[0]-1, pos[2]-pos[1]-1), total_paragraphs - pos[2], pos))
    if not candidates: return {1: 1, 3: 2, 5: 2}
    candidates.sort(key=lambda x: (0 if x[0] <= 3 else 1, 0 if x[1] <= 2 else 1, x[0], x[1]))
    best = candidates[0][2]
    return {best[0]: 1, best[1]: 2, best[2]: 2}


async def remove_all_overlays(page):
    """激进移除所有遮罩层 - CSS隐藏 + DOM移除"""
    await page.evaluate("""
        () => {
            // CSS隐藏所有遮罩
            const style = document.createElement('style');
            style.id = 'anti-mask-style';
            style.textContent = `
                .byte-drawer-mask, .byte-modal-mask, .byte-overlay,
                .byte-drawer-wrapper, .byte-modal-wrapper,
                [class*="drawer-mask"], [class*="modal-mask"],
                [class*="overlay"] { display: none !important; pointer-events: none !important; }
            `;
            document.head.appendChild(style);
            
            // DOM移除已知遮罩
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.5)


async def wait_for_editor(page, timeout=20):
    """等待编辑器就绪，并确保遮罩已清除"""
    for i in range(timeout):
        await asyncio.sleep(1)
        await remove_all_overlays(page)
        ready = await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return false;
                const rect = ed.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }
        """)
        if ready:
            return True
    return False


async def upload_images_get_urls(page, img_bytes_list):
    """上传图片获取服务器URL"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_all_overlays(page)
        
        # 清空编辑器
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = ''; ed.focus(); }
            }
        """)
        await asyncio.sleep(0.3)
        
        # 粘贴图片
        b64 = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return;
                ed.focus();
                const bs = atob("{b64}");
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
        for _ in range(30):
            await asyncio.sleep(1)
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break
        
        ok = img_url and not img_url.startswith('blob:') and not img_url.startswith('data:')
        print("OK" if ok else "FAIL")
        image_urls.append(img_url if ok else "")
        await asyncio.sleep(0.3)
    return image_urls


async def paste_image_url(page, img_url):
    """通过HTML粘贴图片URL"""
    await page.evaluate(f"""
        () => {{
            const ed = document.querySelector('.ProseMirror');
            if (!ed) return;
            ed.focus();
            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
            const cd = {{
                types: ['text/html'],
                getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" />' : ''; }},
                setData: function() {{}}, clearData: function() {{}}, files: [], items: []
            }};
            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
            ed.dispatchEvent(ev);
        }}
    """)


async def process_article(context, cookies, art, index, total):
    """处理单篇文章 - 使用独立页面"""
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
    
    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    print(f"  压缩: {len(img_bytes_list)}张")
    
    # 创建独立页面
    page = await context.new_page()
    
    # 设置请求拦截，捕获保存请求
    save_requests = []
    async def on_request(request):
        url = request.url
        if "save" in url.lower() or "ugc" in url.lower():
            save_requests.append({
                "url": url[:200],
                "method": request.method,
                "post_data": request.post_data,
                "time": time.time()
            })
    page.on("request", on_request)
    
    try:
        print(f"  导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        # 移除遮罩
        await remove_all_overlays(page)
        
        # 关闭弹窗
        try:
            for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(0.5)
        except: pass
        
        await remove_all_overlays(page)
        
        # 等待编辑器就绪
        if not await wait_for_editor(page, 20):
            print("  [ERROR] 编辑器未就绪")
            await page.screenshot(path=f"/workspace/editor_v8_art{index}_error.png")
            return False
        
        print("  [OK] 编辑器就绪")
        
        # 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"  上传图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid = len([u for u in image_urls if u])
            print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")
        
        valid_urls = [u for u in image_urls if u]
        image_layout = calc_image_layout(len(paragraphs), len(valid_urls))
        print(f"  图片布局: {image_layout}")
        
        # 输入内容
        print(f"  输入内容 ({len(paragraphs)}段文字, {len(valid_urls)}张图片)...")
        
        await remove_all_overlays(page)
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = ''; ed.focus(); }
            }
        """)
        await asyncio.sleep(0.3)
        
        img_idx = 0
        t0 = time.time()
        for pi, para_text in enumerate(paragraphs):
            await remove_all_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=0)
            await asyncio.sleep(0.1)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.1)
            
            target_para = pi + 1
            if target_para in image_layout:
                for _ in range(image_layout[target_para]):
                    if img_idx < len(valid_urls):
                        await paste_image_url(page, valid_urls[img_idx])
                        await asyncio.sleep(0.3)
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(0.1)
                        img_idx += 1
        
        print(f"  输入完成 ({time.time()-t0:.1f}s)")
        
        # 填写标题
        print(f"  填写标题...")
        await remove_all_overlays(page)
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        try:
            await title_el.click(timeout=5000)
        except:
            # 尝试通过JS聚焦
            await page.evaluate("""
                () => {
                    const el = document.querySelector('textarea[placeholder*="文章标题"]');
                    if (el) { el.focus(); el.click(); }
                }
            """)
        await asyncio.sleep(0.3)
        await title_el.fill(title)
        await asyncio.sleep(2)
        
        # 触发编辑器事件
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) {
                    ed.dispatchEvent(new Event('input', {bubbles: true}));
                    ed.dispatchEvent(new Event('change', {bubbles: true}));
                    ed.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(2)
        
        # 等待自动保存 - 检测页面上的"草稿已保存"提示
        print(f"  等待自动保存 (60秒)...")
        saved = False
        for i in range(60):
            await asyncio.sleep(1)
            result = await page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                    const btns = document.querySelectorAll('button, span');
                    for (let j = 0; j < btns.length; j++) {
                        if ((btns[j].textContent || '').indexOf('草稿已保存') !== -1) return true;
                    }
                    return false;
                }
            """)
            if result:
                print(f"  [{i+1}s] 保存成功!")
                saved = True
                break
        
        if not saved:
            print(f"  未检测到自动保存，尝试手动触发...")
            # 点击编辑器再输入
            await remove_all_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.focus(); ed.click(); } }")
            await asyncio.sleep(0.5)
            await page.keyboard.press('Space')
            await asyncio.sleep(0.2)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(3)
            
            for i in range(20):
                await asyncio.sleep(1)
                result = await page.evaluate("""
                    () => {
                        const body = document.body.innerText;
                        if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                        return false;
                    }
                """)
                if result:
                    print(f"  [{i+1}s] 保存成功!")
                    saved = True
                    break
        
        # 截图
        await page.screenshot(path=f"/workspace/editor_v8_art{index}.png")
        
        # 打印捕获的保存请求
        if save_requests:
            print(f"  捕获 {len(save_requests)} 个保存请求:")
            for req in save_requests:
                print(f"    {req['method']} {req['url'][:150]}")
        
        return saved
    
    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        await page.screenshot(path=f"/workspace/editor_v8_art{index}_error.png")
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    
    print(f"共 {len(articles)} 篇文章待上传")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])
        
        # 验证登录
        print("验证登录...")
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await page.close()
        
        success = 0
        for i, art in enumerate(articles, 1):
            try:
                if await process_article(context, cookies, art, i, len(articles)):
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [FATAL] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)
        
        # 验证草稿箱
        print(f"\n{'='*60}")
        print(f"验证草稿箱...")
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:40]}")
        
        await page.screenshot(path="/workspace/draft_v8_final.png")
        await page.close()
        await browser.close()
    
    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())