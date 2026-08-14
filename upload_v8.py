#!/usr/bin/env python3
"""v8: 修复保存机制 - 拦截save API + 键盘逐段输入确保状态同步

核心改进:
1. 拦截自动保存API响应，检测7050/成功
2. 使用键盘逐段输入文字+粘贴图片，确保ProseMirror状态同步
3. 每篇完成后验证草稿箱
4. 正确的calc_image_layout算法
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
LOG_FILE = os.path.join(BASE_DIR, "upload_v8.log")

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"{ts} {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def calc_image_layout(total_paragraphs, num_images=5):
    if total_paragraphs < 1: return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0: return {1: 1} if num_images >= 1 else {}
    first = 1
    def _build_positions(last):
        if last < 3: return [first]
        pos_list = [first]
        if n_groups == 1: pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups: raw = last
                else: raw = first + step * k
                pos = int(round(raw))
                min_pos = pos_list[-1] + 2
                remaining_after = n_groups - k
                max_pos = last - 2 * remaining_after
                pos = max(min_pos, min(max_pos, pos))
                pos_list.append(pos)
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list
    def _max_gap(pos_list):
        if len(pos_list) < 2: return 0
        return max(pos_list[i+1] - pos_list[i] - 1 for i in range(len(pos_list) - 1))
    candidates = []
    for tail_target in [2, 3]:
        last_cand = total_paragraphs - tail_target
        if last_cand >= 3:
            positions = _build_positions(last_cand)
            if len(positions) >= 2:
                actual_tail = total_paragraphs - positions[-1]
                gap = _max_gap(positions)
                candidates.append((gap, actual_tail, positions))
    if not candidates: return {1: 1}
    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)
    candidates.sort(key=_score)
    best_positions = candidates[0][2]
    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))

def extract_html_content(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if body_match:
        body = body_match.group(1)
        for m in re.finditer(
            r'(<p>(.*?)</p>)|'
            r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>.*?</div>)',
            body, re.DOTALL
        ):
            if m.group(1):
                clean = re.sub(r"<[^>]+>", "", m.group(2))
                if clean.strip():
                    paragraphs.append(clean.strip())
            elif m.group(4):
                images.append(m.group(4))
    return paragraphs, images

def compress_image(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except Exception as e:
        log(f"  压缩图片失败: {e}")
        return None

async def dismiss_popups(page):
    for _ in range(3):
        try:
            await page.evaluate("""
                () => {
                    document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .ant-modal-mask').forEach(m => m.remove());
                    document.querySelectorAll('button, span').forEach(b => {
                        const t = (b.textContent || '').trim();
                        if (['关闭','取消','知道了','不恢复'].includes(t)) b.click();
                    });
                }
            """)
            await asyncio.sleep(0.5)
        except:
            break

async def paste_image_to_editor(page, img_bytes):
    """将图片通过粘贴事件插入编辑器，返回服务器URL"""
    b64 = base64.b64encode(img_bytes).decode('ascii')
    await page.evaluate("""
        (b64) => {
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return;
            editor.focus();
            const byteString = atob(b64);
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
            const blob = new Blob([ab], {type: 'image/jpeg'});
            const file = new File([blob], 'img.jpg', {type: 'image/jpeg'});
            const dt = new DataTransfer();
            dt.items.add(file);
            const pasteEvent = new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt
            });
            editor.dispatchEvent(pasteEvent);
        }
    """, b64)
    
    # 等待图片上传完成
    for i in range(90):
        img_url = await page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('.ProseMirror img');
                if (imgs.length === 0) return '';
                return imgs[imgs.length - 1].src || '';
            }
        """)
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
        await asyncio.sleep(1)
    return ""

async def type_text_to_editor(page, text):
    """通过键盘逐字输入文字到编辑器"""
    # 使用剪贴板粘贴整段文字（比逐字输入更快）
    escaped = json.dumps(text)
    await page.evaluate(f"""
        () => {{
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return;
            editor.focus();
            const text = {escaped};
            const dt = new DataTransfer();
            dt.setData('text/plain', text);
            const pasteEvent = new ClipboardEvent('paste', {{
                bubbles: true, cancelable: true, clipboardData: dt
            }});
            editor.dispatchEvent(pasteEvent);
        }}
    """)
    await asyncio.sleep(0.5)

async def process_article(context, art, index, total):
    category = art.get("category", "未知")
    title = art.get("title", "")[:30]
    html_path = art.get("html_file", "")
    
    log(f"\n{'='*60}")
    log(f"[{index}/{total}] {category} - {title}")
    log(f"{'='*60}")
    
    if not os.path.exists(html_path):
        log(f"  [ERROR] HTML文件不存在: {html_path}")
        return False
    
    paragraphs, images_base64 = extract_html_content(html_path)
    log(f"  提取: {len(paragraphs)}段文字, {len(images_base64)}张图片")
    
    # 压缩图片
    img_bytes_list = []
    for img in images_base64:
        compressed = compress_image(img)
        if compressed:
            img_bytes_list.append(compressed)
    log(f"  压缩: {len(img_bytes_list)}张有效图片")
    
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    log(f"  图片布局: {image_layout}")
    
    page = await context.new_page()
    
    # 拦截保存请求
    save_results = []
    
    async def on_response(response):
        url = response.url
        if 'save_ugc_draft' in url or 'article/publish' in url or 'auto_save' in url:
            try:
                body = await response.json()
                save_results.append({"url": url, "code": body.get("code"), "msg": body.get("message", "")})
                log(f"  [SAVE API] code={body.get('code')} msg={body.get('message','')}")
            except:
                pass
    
    page.on("response", on_response)
    
    try:
        # [1] 打开发布页面
        log(f"  [1] 打开全新发布页面...")
        await page.goto(PUBLISH_URL + "?_t=" + str(int(time.time() * 1000)),
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_popups(page)
        await asyncio.sleep(1)
        
        for i in range(20):
            pm_exists = await page.evaluate("() => !!document.querySelector('.ProseMirror')")
            if pm_exists:
                log(f"  [OK] 编辑器就绪")
                break
            await asyncio.sleep(1)
        else:
            log(f"  [ERROR] 编辑器加载超时")
            await page.close()
            return False
        
        await dismiss_popups(page)
        await asyncio.sleep(1)
        
        # [2] 清空编辑器
        log(f"  [2] 清空编辑器...")
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.innerHTML = '';
                    editor.focus();
                }
            }
        """)
        await asyncio.sleep(1)
        
        # [3] 填标题
        log(f"  [3] 填标题: {title}")
        title_json = json.dumps(title)
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, {title_json});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }}
        """)
        await asyncio.sleep(2)
        
        # [4] 按布局逐段输入文字+图片
        log(f"  [4] 逐段输入内容（{len(paragraphs)}段文字, {len(img_bytes_list)}张图片）...")
        
        img_idx = 0
        for p_idx, para_text in enumerate(paragraphs):
            para_num = p_idx + 1
            
            # 输入文字段落
            await type_text_to_editor(page, para_text)
            # 在段落末尾按回车
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.3)
            
            log(f"    段落{para_num}: OK")
            
            # 检查是否需要在此段落后插入图片
            imgs_needed = image_layout.get(para_num, 0)
            for _ in range(imgs_needed):
                if img_idx < len(img_bytes_list):
                    log(f"    图片{img_idx+1}: 粘贴中...")
                    img_url = await paste_image_to_editor(page, img_bytes_list[img_idx])
                    if img_url:
                        log(f"    图片{img_idx+1}: OK ({img_url[:50]}...)")
                        # 图片后按回车
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(0.3)
                    else:
                        log(f"    图片{img_idx+1}: FAIL")
                    img_idx += 1
            
            await asyncio.sleep(0.3)
        
        log(f"  [4] 完成: {img_idx}张图片已插入")
        
        # [5] 等待保存
        log(f"  [5] 等待自动保存...")
        
        # 修改标题触发自动保存
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                const origTitle = {title_json};
                el.focus();
                ns.call(el, origTitle + ' ');
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        """)
        await asyncio.sleep(0.5)
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, {title_json});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }}
        """)
        
        # 等待保存响应
        save_success = False
        for i in range(20):
            await asyncio.sleep(1)
            if save_results:
                last = save_results[-1]
                if last.get("code") == 0:
                    save_success = True
                    log(f"  [OK] 保存成功确认")
                    break
                elif last.get("code") == 7050:
                    log(f"  [WARN] 保存返回7050: {last.get('msg')}")
                    break
                elif last.get("code") is not None:
                    log(f"  [WARN] 保存返回{last.get('code')}: {last.get('msg')}")
        
        if not save_success and not any(r.get("code") == 0 for r in save_results):
            log(f"  [WARN] 未收到保存成功响应，尝试点击预览触发保存...")
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button, span, div[role="button"]');
                    for (const b of btns) {
                        if ((b.textContent || '').trim() === '预览') {
                            b.click();
                            return;
                        }
                    }
                }
            """)
            await asyncio.sleep(5)
            await page.evaluate("""
                () => {
                    document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask').forEach(m => m.remove());
                    const btns = document.querySelectorAll('button, span');
                    for (const b of btns) {
                        if ((b.textContent || '').trim() === '关闭') { b.click(); return; }
                    }
                }
            """)
            await asyncio.sleep(2)
        
        # [6] 验证草稿箱
        log(f"  [6] 验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(5)
        
        draft_html = await page.evaluate("() => document.body.innerText")
        search_key = title[:15]
        found = search_key in draft_html
        
        if found:
            log(f"  [SUCCESS] 文章已在草稿箱中!")
            await page.close()
            return True
        else:
            log(f"  [FAIL] 未在草稿箱中找到文章(搜索:{search_key})")
            # 打印草稿箱中的文章标题
            draft_titles = re.findall(r'编辑删除\n(.+?)\n', draft_html)
            if draft_titles:
                log(f"  草稿箱现有文章: {draft_titles[:5]}")
            await page.close()
            return False
            
    except Exception as e:
        log(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        try:
            await page.close()
        except:
            pass
        return False

async def main():
    log("=" * 60)
    log(f"头条草稿箱上传 v8 - 键盘逐段输入+保存拦截")
    log("=" * 60)
    
    if not os.path.exists(MANIFEST_FILE):
        log(f"[ERROR] manifest不存在: {MANIFEST_FILE}")
        return
    
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    log(f"共{len(manifest)}篇文章待上传")
    
    log("启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-dev-shm-usage', '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, "r") as f:
                cookie_data = json.load(f)
            await context.add_cookies([
                {"name": n, "value": str(v), "domain": ".toutiao.com", "path": "/"}
                for n, v in cookie_data.items()
            ])
            log("Cookie已加载")
        
        # 验证登录
        page = await context.new_page()
        await page.goto("https://mp.toutiao.com/profile_v4/index", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        current_url = page.url
        log(f"当前URL: {current_url}")
        
        if "login" in current_url.lower() or "passport" in current_url.lower():
            log("[ERROR] Cookie已过期，需要重新登录")
            await browser.close()
            return
        
        log("[OK] 登录有效")
        await page.close()
        
        # 逐篇处理
        success_count = 0
        for i, art in enumerate(manifest):
            result = await process_article(context, art, i+1, len(manifest))
            if result:
                success_count += 1
            await asyncio.sleep(3)
        
        log(f"\n{'='*60}")
        log(f"完成: {success_count}/{len(manifest)}篇上传成功")
        log(f"{'='*60}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())