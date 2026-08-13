#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""针对文章2（邹市明）的单独上传脚本，增强保存触发"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"

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

PM_SET_CONTENT_JS = """(() => {
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

async def upload_single_image(page, img_bytes, img_index):
    b64_str = base64.b64encode(img_bytes).decode('ascii')
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
            const pasteEvent = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
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
    for _ in range(30):
        await asyncio.sleep(1)
        has_img = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0")
        if has_img:
            break
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
    img_url = ""
    for _ in range(60):
        img_url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
        await asyncio.sleep(1)
    for _ in range(30):
        await asyncio.sleep(2)
        img_url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
    return img_url

async def main():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    # Article 2
    title = "45岁重返拳台，左眼几近失明，邹市明图什么"
    html_path = "/workspace/output/tt_hot_tt_体育_2_20260813_093751.html"

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        await context.grant_permissions(["clipboard-read", "clipboard-write"])
        cookie_list = [{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 验证登录
        print("验证登录...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie过期")
            await browser.close()
            return
        print("[OK] 已登录")

        # 导航到发布页
        print("导航到发布页...")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 清理遮罩
        for _ in range(3):
            try:
                for btn_text in ["不恢复", "关闭", "取消", "我知道了"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1)
                        break
            except:
                pass
            await page.evaluate("""
                () => {
                    document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
                    document.querySelectorAll('.byte-drawer-wrapper, .byte-modal-wrapper').forEach(w => w.remove());
                }
            """)
            await asyncio.sleep(0.5)

        try:
            await page.wait_for_selector(".ProseMirror", timeout=15000)
            print("[OK] 编辑器就绪")
        except:
            print("[ERROR] 编辑器未就绪")
            return

        # 填标题
        print("填标题...")
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        try:
            await title_el.click(timeout=5000)
        except:
            await page.evaluate("() => { const e = document.querySelector('textarea[placeholder*=\"文章标题\"]'); if(e) e.focus(); }")
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(2)

        # 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"上传{len(img_bytes_list)}张图片...")
            for img_idx, img_bytes in enumerate(img_bytes_list):
                print(f"  图片{img_idx+1}: 上传中...")
                img_url = await upload_single_image(page, img_bytes, img_idx + 1)
                if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                    image_urls.append(img_url)
                    print(f"  图片{img_idx+1}: OK")
                else:
                    print(f"  图片{img_idx+1}: FAIL")
                    image_urls.append("")
                await asyncio.sleep(0.5)
            print(f"上传完成: {len([u for u in image_urls if u])}/{len(img_bytes_list)}张")

        # 图片布局
        n_imgs = len([u for u in image_urls if u])
        image_layout = {}
        if n_imgs >= 5:
            image_layout = {1: 1, 3: 2, 5: 2}
        elif n_imgs >= 3:
            image_layout = {1: 1, 3: 2}
        elif n_imgs >= 1:
            image_layout = {1: 1}

        # 通过ProseMirror设置内容
        print("设置内容 (ProseMirror)...")
        pm_data = {"tp": paragraphs, "iu": image_urls, "il": image_layout}
        await page.evaluate(f"window._pmData = {json.dumps(pm_data, ensure_ascii=False)};")
        await asyncio.sleep(0.3)
        pm_result = await page.evaluate(PM_SET_CONTENT_JS)
        print(f"PM结果: {pm_result}")

        try:
            pm_json = json.loads(pm_result)
        except:
            pm_json = {"status": "parse_error"}

        if pm_json.get("status") != "ok":
            print(f"[ERROR] ProseMirror设置失败")
            await browser.close()
            return

        print(f"[OK] ProseMirror: {pm_json.get('chars')}字, {pm_json.get('imgs')}张图片")

        # === 增强保存触发 ===
        print("触发保存...")

        # 清理遮罩
        await page.evaluate("""
            () => {
                document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
                document.querySelectorAll('.byte-drawer-wrapper, .byte-modal-wrapper').forEach(w => w.remove());
            }
        """)
        await asyncio.sleep(0.5)

        # 方法1: 标题native setter + blur
        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, el.value + ' ');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                setTimeout(() => {
                    ns.call(el, el.value.slice(0, -1));
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.blur();
                }, 300);
            }
        """)
        await asyncio.sleep(1)

        # 方法2: 正文键盘编辑
        try:
            editor = page.locator(".ProseMirror").first
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

        # 方法3: 标题blur触发
        try:
            await title_el.click(timeout=5000)
        except:
            await page.evaluate("() => { const e = document.querySelector('textarea[placeholder*=\"文章标题\"]'); if(e) { e.focus(); e.click(); } }")
        await asyncio.sleep(0.5)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.5)

        # 方法4: 检查是否有保存按钮，但不点击（可能有问题）
        # 相反，我们通过多次导航来触发自动保存

        # 等待并检查保存提示
        print("等待保存...")
        for i in range(30):
            await asyncio.sleep(1)
            body_text = await page.evaluate("() => document.body.innerText || ''")
            if "草稿已保存" in body_text or "保存成功" in body_text:
                print(f"  [OK] 保存提示 (第{i+1}秒)")
                break
            if i == 10 or i == 20:
                # 重新触发编辑
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

        # 直接导航到草稿页验证（导航本身会触发保存）
        print("导航到草稿页验证...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        draft_text = await page.evaluate("() => document.body.innerText || ''")
        search_key = title[:8]
        if search_key in draft_text:
            print(f"[SUCCESS] 文章已在草稿箱中!")
            idx = draft_text.find(search_key)
            print(f"  {draft_text[max(0,idx-20):idx+100]}")
        else:
            print(f"[FAIL] 未找到 (页面长度: {len(draft_text)})")
            print(f"  页面: {draft_text[:500]}")

            # 最后尝试：回到发布页，手动触发保存，再回来
            print("最终尝试: 返回发布页重新触发...")
            await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(5)

            # 检查是否有"恢复草稿"弹窗
            try:
                for btn_text in ["不恢复", "恢复", "确定"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1)
            except:
                pass

            await page.evaluate("""
                () => {
                    document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
                }
            """)
            await asyncio.sleep(1)

            # 重新设置内容
            print("  重新设置PM内容...")
            await page.evaluate(f"window._pmData = {json.dumps(pm_data, ensure_ascii=False)};")
            await asyncio.sleep(0.3)
            await page.evaluate(PM_SET_CONTENT_JS)
            await asyncio.sleep(2)

            # 标题编辑触发
            await page.evaluate("""
                () => {
                    const el = document.querySelector('textarea[placeholder*="文章标题"]');
                    if (!el) return;
                    el.focus();
                    const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    ns.call(el, el.value + 'x');
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    setTimeout(() => {
                        ns.call(el, el.value.slice(0, -1));
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.blur();
                    }, 200);
                }
            """)
            await asyncio.sleep(2)

            # 正文编辑
            await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
            await asyncio.sleep(0.3)
            await page.keyboard.press("End")
            await asyncio.sleep(0.2)
            await page.keyboard.type(" x", delay=50)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)

            # 等待保存
            print("  等待保存...")
            await asyncio.sleep(20)

            # 再次验证
            await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(5)
            draft_text = await page.evaluate("() => document.body.innerText || ''")
            if search_key in draft_text:
                print(f"[SUCCESS] 文章已在草稿箱中! (最终尝试)")
            else:
                print(f"[FAIL] 最终尝试也失败了 (页面长度: {len(draft_text)})")
                print(f"  页面: {draft_text[:500]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())