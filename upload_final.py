#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Playwright + ProseMirror view.dispatch() 上传文章到头条草稿箱（Linux）

核心策略：
1. 逐张粘贴图片触发上传 → 获取服务器URL
2. 通过 ProseMirror view.dispatch() 设置完整内容（确保内部状态同步，解决7050错误）
3. 触发自动保存 → 验证草稿箱
"""
import os, re, json, time, base64, asyncio, io, sys
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"

# ── 工具函数 ──

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

# ── ProseMirror view.dispatch() 内容设置 ──

PM_SET_CONTENT_JS = """(() => {
    // 查找 ProseMirror view
    function findView() {
        var editor = document.querySelector('.ProseMirror');
        if (!editor) return null;
        var desc = editor.pmViewDesc;
        while (desc) {
            if (desc.view && desc.view.state) return desc.view;
            desc = desc.parent;
        }
        function sf(fiber, v) {
            if (!fiber || v.has(fiber) || v.size > 500) return null;
            v.add(fiber);
            if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
            if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
            if (fiber.memoizedState) {
                var s = fiber.memoizedState;
                while (s) {
                    if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view;
                    s = s.next;
                }
            }
            var r = sf(fiber.child, v);
            if (r) return r;
            return sf(fiber.sibling, v);
        }
        var el = editor;
        for (var i = 0; i < 15 && el; i++) {
            var fk = Object.keys(el).find(function(k) {
                return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0;
            });
            if (fk) {
                var v = new Set();
                var r = sf(el[fk], v);
                if (r) return r;
            }
            el = el.parentElement;
        }
        return null;
    }
    var view = findView();
    if (!view) return JSON.stringify({status: 'no_view'});

    var schema = view.state.schema;
    var nts = Object.keys(schema.nodes);

    // 推断节点类型名称
    var pn = null, im = null, dn = null;
    nts.forEach(function(k) {
        if (k === 'paragraph' || k === 'para') pn = k;
        if (k === 'doc') dn = k;
        if (k === 'image' || k === 'imageUpload' || k === 'media' || k === 'img') im = k;
    });
    if (!im) nts.forEach(function(k) {
        if (k.toLowerCase().indexOf('image') >= 0 || k.toLowerCase().indexOf('media') >= 0) im = k;
    });
    if (!pn) nts.forEach(function(k) {
        if (k.toLowerCase().indexOf('para') >= 0) pn = k;
    });
    if (!dn) nts.forEach(function(k) {
        if (k === 'doc' || k === 'document' || k === 'article') dn = k;
    });
    if (!pn || !dn) return JSON.stringify({status: 'no_types', nodes: nts});

    // 推断图片节点属性
    var urlAttr = 'src';
    var imAttrs = {};
    if (im) {
        var imSpec = schema.nodes[im];
        if (imSpec && imSpec.spec && imSpec.spec.attrs) {
            Object.keys(imSpec.spec.attrs).forEach(function(an) {
                var a = imSpec.spec.attrs[an];
                if (an === 'src' || an === 'url' || an === 'href') urlAttr = an;
                imAttrs[an] = a && a.default !== undefined ? a.default : '[no-default]';
            });
        }
    }

    var data = window._pmData;
    if (!data) return JSON.stringify({status: 'no_data'});

    var content = [];
    var ui = 0;
    var hasDataAttr = imAttrs && Object.keys(imAttrs).indexOf('data') >= 0;

    for (var i = 0; i < data.tp.length; i++) {
        if (data.tp[i]) {
            content.push({type: pn, content: [{type: 'text', text: data.tp[i]}]});
        }
        var t = i + 1;
        if (data.il && data.il[t]) {
            for (var j = 0; j < data.il[t]; j++) {
                if (ui < data.iu.length && data.iu[ui]) {
                    var imgUrl = data.iu[ui];
                    var attrs = {};
                    if (hasDataAttr) {
                        attrs.data = {
                            url: imgUrl, icUri: imgUrl, catchErrorUrl: "",
                            link: "", caption: "图片来源于网络", ic: false,
                            naturalHeight: 0, naturalWidth: 0, srcType: "",
                            captionLenErr: false, needCheck: false
                        };
                    } else {
                        attrs[urlAttr] = imgUrl;
                        attrs.alt = '图片来源于网络';
                    }
                    content.push({type: im, attrs: attrs});
                    ui++;
                }
            }
        }
    }

    try {
        var doc = schema.nodeFromJSON({type: dn, content: content});
        view.dispatch(view.state.tr.replaceWith(0, view.state.doc.content.size, doc.content));
        var ic = 0;
        view.state.doc.descendants(function(node) {
            if (node.type.name === im) ic++;
            return true;
        });
        return JSON.stringify({
            status: 'ok', imgs: ic, chars: view.state.doc.textContent.length,
            nodes: nts, pn: pn, in: im, urlAttr: urlAttr
        });
    } catch (e) {
        return JSON.stringify({status: 'error', error: e.message, nodes: nts, pn: pn, in: im});
    }
})()"""

# ── 图片上传 ──

async def upload_single_image(page, img_bytes, img_index):
    """粘贴图片文件触发上传，返回服务器URL"""
    b64_str = base64.b64encode(img_bytes).decode('ascii')

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

    # 聚焦并粘贴
    await page.evaluate(f"""
        () => {{
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return;
            editor.focus();
            const b64 = "{b64_str}";
            const byteString = atob(b64);
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
            const blob = new Blob([ab], {{type: 'image/jpeg'}});
            const file = new File([blob], 'image_{img_index}.jpg', {{type: 'image/jpeg'}});
            const pasteEvent = new ClipboardEvent('paste', {{
                bubbles: true, cancelable: true
            }});
            const fakeData = {{
                files: [file], items: [], types: ['Files'],
                getData: function() {{ return ''; }},
                setData: function() {{}},
                clearData: function() {{}}
            }};
            Object.defineProperty(pasteEvent, 'clipboardData', {{
                value: fakeData, writable: false, configurable: true
            }});
            editor.dispatchEvent(pasteEvent);
        }}
    """)

    # 等待图片出现
    for _ in range(30):
        await asyncio.sleep(1)
        has_img = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0")
        if has_img:
            break

    # 删除多余图片，只保留第一张
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return;
            const imgs = editor.querySelectorAll('img');
            for (let i = imgs.length - 1; i > 0; i--) {
                imgs[i].parentNode.removeChild(imgs[i]);
            }
        }
    """)
    await asyncio.sleep(0.5)

    # 等待图片URL变为服务器URL
    img_url = ""
    for _ in range(60):
        img_url = await page.evaluate("""
            () => {
                const img = document.querySelector('.ProseMirror img');
                return img ? img.src : '';
            }
        """)
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
        await asyncio.sleep(1)

    # 额外等待
    for _ in range(30):
        await asyncio.sleep(2)
        img_url = await page.evaluate("""
            () => {
                const img = document.querySelector('.ProseMirror img');
                return img ? img.src : '';
            }
        """)
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url

    return img_url


# ── 单篇文章上传 ──

async def upload_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 未提取到文字内容")
        return False

    # 压缩图片
    print(f"  压缩图片...")
    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩完成: {len(img_bytes_list)}张")

    # 导航到发布页面
    print(f"  导航到发布页面...")
    await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗和遮罩（多次尝试，确保清理干净）
    for attempt in range(3):
        try:
            # 关闭弹窗按钮
            for btn_text in ["不恢复", "关闭", "取消", "我知道了"]:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except:
            pass
        # 强制移除所有遮罩层
        try:
            await page.evaluate("""
                () => {
                    const masks = document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay');
                    masks.forEach(m => m.remove());
                    const wrappers = document.querySelectorAll('.byte-drawer-wrapper, .byte-modal-wrapper');
                    wrappers.forEach(w => w.remove());
                }
            """)
            await asyncio.sleep(0.5)
        except:
            pass
        # 检查是否还有遮罩
        try:
            has_mask = await page.evaluate("() => document.querySelector('.byte-drawer-mask') !== null")
            if not has_mask:
                break
        except:
            break
        await asyncio.sleep(1)

    # 等待编辑器
    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
        print("  [OK] 编辑器已就绪")
    except:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 填标题
    print(f"  填标题...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    try:
        await title_el.click(timeout=5000)
    except:
        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (el) { el.focus(); el.click(); }
            }
        """)
    await asyncio.sleep(0.5)
    await title_el.fill(title)
    await asyncio.sleep(2)

    # ── 第1步：逐张上传图片，获取服务器URL ──
    image_urls = []
    if img_bytes_list:
        print(f"  上传{len(img_bytes_list)}张图片...")
        for img_idx, img_bytes in enumerate(img_bytes_list):
            print(f"    图片{img_idx+1}: 上传中...")
            img_url = await upload_single_image(page, img_bytes, img_idx + 1)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                image_urls.append(img_url)
                print(f"    图片{img_idx+1}: OK ({img_url[:70]}...)")
            else:
                print(f"    图片{img_idx+1}: FAIL (url={img_url[:50] if img_url else 'empty'})")
                image_urls.append("")
            await asyncio.sleep(0.5)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    # 计算图片布局
    n_imgs = len([u for u in image_urls if u])
    image_layout = {}
    if n_imgs >= 5:
        image_layout = {1: 1, 3: 2, 5: 2}
    elif n_imgs >= 3:
        image_layout = {1: 1, 3: 2}
    elif n_imgs >= 1:
        image_layout = {1: 1}

    # ── 第2步：通过 ProseMirror view.dispatch() 设置内容 ──
    print(f"  设置内容 (ProseMirror view.dispatch)...")
    pm_data = {
        "tp": paragraphs,        # text paragraphs
        "iu": image_urls,        # image URLs
        "il": image_layout       # image layout
    }
    await page.evaluate(f"window._pmData = {json.dumps(pm_data, ensure_ascii=False)};")
    await asyncio.sleep(0.3)

    pm_result = await page.evaluate(PM_SET_CONTENT_JS)
    print(f"  PM结果: {pm_result}")

    try:
        pm_json = json.loads(pm_result)
    except:
        pm_json = {"status": "parse_error"}

    if pm_json.get("status") == "ok":
        chars = pm_json.get("chars", 0)
        imgs = pm_json.get("imgs", 0)
        print(f"  [OK] ProseMirror: {chars}字, {imgs}张图片")
    else:
        print(f"  [WARN] ProseMirror失败: {pm_result}, 回退innerHTML...")
        # 回退：用 innerHTML 构建HTML
        content_parts = []
        img_idx = 0
        for para_idx, para_text in enumerate(paragraphs):
            content_parts.append(f"<p>{para_text}</p>")
            target_para = para_idx + 1
            if target_para in image_layout:
                num_imgs = image_layout[target_para]
                for _ in range(num_imgs):
                    if img_idx < len(image_urls) and image_urls[img_idx]:
                        content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt="图片来源于网络"></p>')
                        img_idx += 1
        content_html = "\n".join(content_parts)

        await page.evaluate(f"""
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (editor) {{
                    editor.innerHTML = {json.dumps(content_html)};
                    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
            }}
        """)
        await asyncio.sleep(2)

    # ── 第3步：触发保存 ──
    print(f"  触发保存...")

    # 策略1：通过原生value setter修改标题触发React状态更新 + blur
    # 这是最可靠的触发方式（参考upload_visible.py的trigger_save）
    await page.evaluate("""
        () => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return 'no_title';
            el.focus();
            // 修改标题值（添加空格再删除，触发change）
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeSetter.call(el, el.value + ' ');
            el.dispatchEvent(new Event('input', {bubbles: true}));
            // 恢复
            setTimeout(() => {
                nativeSetter.call(el, el.value.slice(0, -1));
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
            }, 300);
            return 'ok';
        }
    """)
    await asyncio.sleep(1)

    # 策略2：在正文区域用键盘做一次真实编辑（触发ProseMirror onChange）
    editor = page.locator(".ProseMirror").first
    try:
        await editor.click(timeout=5000)
    except:
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
    await asyncio.sleep(0.5)
    await page.keyboard.press("End")
    await asyncio.sleep(0.3)
    await page.keyboard.type(" ", delay=50)
    await asyncio.sleep(0.3)
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.5)

    # 策略3：点击标题区域触发blur（blur时通常触发auto-save）
    # 先确保遮罩层已清理
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
            document.querySelectorAll('.byte-drawer-wrapper, .byte-modal-wrapper').forEach(w => w.remove());
        }
    """)
    await asyncio.sleep(0.3)
    try:
        await title_el.click(timeout=5000)
    except:
        # 被遮罩拦截，用JS点击
        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (el) { el.focus(); el.click(); }
            }
        """)
    await asyncio.sleep(0.5)
    await page.keyboard.press("Tab")  # 切换到正文，触发标题blur
    await asyncio.sleep(0.5)

    # 策略4：尝试点击"保存草稿"按钮（如果有的话）
    try:
        save_btn = page.locator("button:has-text('保存'), button:has-text('草稿'), span:has-text('保存')").first
        if await save_btn.is_visible(timeout=2000):
            await save_btn.click()
            print(f"  点击了保存按钮")
            await asyncio.sleep(2)
    except:
        pass

    # 等待自动保存，同时检查是否有"草稿已保存"提示
    print(f"  等待自动保存...")
    saved = False
    for i in range(20):
        await asyncio.sleep(1)
        body_text = await page.evaluate("() => document.body.innerText || ''")
        if "草稿已保存" in body_text or "保存成功" in body_text:
            print(f"  [OK] 检测到保存提示 (第{i+1}秒)")
            saved = True
            break
        # 每5秒重新触发一次编辑
        if i == 5:
            try:
                await editor.click(timeout=3000)
            except:
                await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
            await asyncio.sleep(0.3)
            await page.keyboard.press("End")
            await asyncio.sleep(0.2)
            await page.keyboard.type(" ", delay=50)
            await asyncio.sleep(0.2)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            try:
                await title_el.click(timeout=3000)
            except:
                await page.evaluate("() => { const e = document.querySelector('textarea[placeholder*=\"文章标题\"]'); if(e) e.focus(); }")
            await asyncio.sleep(0.3)

    if not saved:
        print(f"  [WARN] 未检测到保存提示，再等待10秒...")
        await asyncio.sleep(10)

    # ── 第4步：验证草稿箱 ──
    print(f"  验证草稿箱...")
    await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    draft_text = await page.evaluate("() => document.body.innerText || ''")

    # 使用标题前8个字符搜索
    search_key = title[:8]
    if search_key in draft_text:
        idx = draft_text.find(search_key)
        snippet = draft_text[max(0, idx-20):idx+100]
        print(f"  [SUCCESS] 文章已在草稿箱中!")
        print(f"    匹配: ...{snippet}...")
        return True

    # 重试
    print(f"  首次验证失败，等待10秒后重试...")
    await asyncio.sleep(10)
    await page.reload(wait_until="domcontentloaded")
    await asyncio.sleep(5)
    draft_text = await page.evaluate("() => document.body.innerText || ''")

    if search_key in draft_text:
        print(f"  [SUCCESS] 文章已在草稿箱中! (重试后)")
        return True

    # 页面太短说明可能没加载
    if len(draft_text) < 100:
        print(f"  [WARN] 草稿页面内容过短({len(draft_text)}字符)，可能未加载")
    else:
        print(f"  [FAIL] 未在草稿箱中找到 (页面长度: {len(draft_text)})")
        print(f"  页面内容预览: {draft_text[:500]}")

    return False


# ── 主流程 ──

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await context.grant_permissions(["clipboard-read", "clipboard-write"])
        cookie_list = [
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ]
        await context.add_cookies(cookie_list)

        page = await context.new_page()

        # 验证登录
        print("验证登录状态...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期，请重新登录")
            await browser.close()
            return
        print("[OK] 登录状态有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await upload_article(page, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇成功")


if __name__ == "__main__":
    asyncio.run(main())