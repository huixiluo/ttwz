#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文章2用innerHTML方式单独测试"""
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

async def upload_single_image(page, img_bytes, img_index):
    b64_str = base64.b64encode(img_bytes).decode('ascii')
    await page.evaluate("""
        () => { const e = document.querySelector('.ProseMirror'); if(e) { e.innerHTML='<p></p>'; e.dispatchEvent(new Event('input',{bubbles:true})); } }
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
            const blob = new Blob([ab], {{type:'image/jpeg'}});
            const file = new File([blob],'img.jpg',{{type:'image/jpeg'}});
            const pe = new ClipboardEvent('paste',{{bubbles:true,cancelable:true}});
            const fd = {{files:[file],items:[],types:['Files'],getData:()=>'',setData:()=>{{}},clearData:()=>{{}}}};
            Object.defineProperty(pe,'clipboardData',{{value:fd,writable:false,configurable:true}});
            editor.dispatchEvent(pe);
        }}
    """)
    for _ in range(30):
        await asyncio.sleep(1)
        if await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0"):
            break
    await page.evaluate("""
        () => { const e=document.querySelector('.ProseMirror'); if(!e)return; const imgs=e.querySelectorAll('img'); for(let i=imgs.length-1;i>0;i--) imgs[i].parentNode.removeChild(imgs[i]); }
    """)
    await asyncio.sleep(0.5)
    img_url = ""
    for _ in range(60):
        img_url = await page.evaluate("() => { const i=document.querySelector('.ProseMirror img'); return i?i.src:''; }")
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
        await asyncio.sleep(1)
    for _ in range(30):
        await asyncio.sleep(2)
        img_url = await page.evaluate("() => { const i=document.querySelector('.ProseMirror img'); return i?i.src:''; }")
        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
    return img_url

async def main():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    title = "45岁重返拳台，左眼几近失明，邹市明图什么"
    html_path = "/workspace/output/tt_hot_tt_体育_2_20260813_093751.html"

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"段落: {len(paragraphs)}段, 图片: {len(images)}张")

    img_bytes_list = []
    for img in images:
        c = compress_image_to_bytes(img)
        if c: img_bytes_list.append(c)
    print(f"压缩: {len(img_bytes_list)}张")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(viewport={"width":1920,"height":1080})
        await ctx.grant_permissions(["clipboard-read","clipboard-write"])
        await ctx.add_cookies([{"name":k,"value":v,"domain":".toutiao.com","path":"/"} for k,v in cookies.items()])
        page = await ctx.new_page()

        print("验证登录...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("Cookie过期"); return

        print("导航发布页...")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 清理遮罩
        for _ in range(3):
            try:
                for t in ["不恢复","关闭","取消","我知道了"]:
                    b = page.locator(f"button:has-text('{t}')").first
                    if await b.is_visible(timeout=2000): await b.click(); await asyncio.sleep(1); break
            except: pass
            await page.evaluate("()=>{document.querySelectorAll('.byte-drawer-mask,.byte-modal-mask,.byte-overlay').forEach(m=>m.remove());document.querySelectorAll('.byte-drawer-wrapper,.byte-modal-wrapper').forEach(w=>w.remove());}")
            await asyncio.sleep(0.5)

        await page.wait_for_selector(".ProseMirror", timeout=15000)

        # 填标题
        print("填标题...")
        tel = page.locator('textarea[placeholder*="文章标题"]').first
        try: await tel.click(timeout=5000)
        except: await page.evaluate("()=>{const e=document.querySelector('textarea[placeholder*=\"文章标题\"]');if(e)e.focus();}")
        await asyncio.sleep(0.5)
        await tel.fill(title)
        await asyncio.sleep(2)

        # 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"上传{len(img_bytes_list)}张图片...")
            for idx, ib in enumerate(img_bytes_list):
                print(f"  图片{idx+1}...")
                u = await upload_single_image(page, ib, idx+1)
                if u and not u.startswith('blob:') and not u.startswith('data:'):
                    image_urls.append(u); print(f"    OK")
                else:
                    image_urls.append(""); print(f"    FAIL")
                await asyncio.sleep(0.5)
            print(f"上传完成: {len([u for u in image_urls if u])}/{len(img_bytes_list)}张")

        # 图片布局
        valid = len([u for u in image_urls if u])
        il = {}
        if valid >= 5: il = {1:1,3:2,5:2}
        elif valid >= 3: il = {1:1,3:2}
        elif valid >= 1: il = {1:1}

        # === 用 innerHTML 方式设置内容（非ProseMirror） ===
        print("设置内容 (innerHTML)...")
        parts = []
        ui = 0
        for pi, pt in enumerate(paragraphs):
            parts.append(f"<p>{pt}</p>")
            t = pi + 1
            if t in il:
                for _ in range(il[t]):
                    if ui < len(image_urls) and image_urls[ui]:
                        parts.append(f'<p><img src="{image_urls[ui]}" alt="图片来源于网络"></p>')
                        ui += 1
        content_html = "\n".join(parts)

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

        # 验证DOM
        dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
        dom_text = await page.evaluate("() => document.querySelector('.ProseMirror').innerText.length")
        print(f"  DOM: {dom_text}字, {dom_imgs}张图片")

        # 触发保存
        print("触发保存...")
        await page.evaluate("()=>{document.querySelectorAll('.byte-drawer-mask,.byte-modal-mask,.byte-overlay').forEach(m=>m.remove());}")
        await asyncio.sleep(0.3)

        # 标题编辑
        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if(!el)return;
                el.focus();
                const ns=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
                ns.call(el,el.value+' ');
                el.dispatchEvent(new Event('input',{bubbles:true}));
                setTimeout(()=>{ns.call(el,el.value.slice(0,-1));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();},300);
            }
        """)
        await asyncio.sleep(1)

        # 正文编辑
        try:
            ed = page.locator(".ProseMirror").first
            await ed.click(timeout=5000)
        except:
            await page.evaluate("()=>{const e=document.querySelector('.ProseMirror');if(e)e.focus();}")
        await asyncio.sleep(0.5)
        await page.keyboard.press("End")
        await asyncio.sleep(0.3)
        await page.keyboard.type(" ", delay=50)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.5)

        # 标题blur
        try: await tel.click(timeout=5000)
        except: await page.evaluate("()=>{const e=document.querySelector('textarea[placeholder*=\"文章标题\"]');if(e){e.focus();e.click();}}")
        await asyncio.sleep(0.5)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.5)

        print("等待保存...")
        for i in range(30):
            await asyncio.sleep(1)
            bt = await page.evaluate("()=>document.body.innerText||''")
            if "草稿已保存" in bt or "保存成功" in bt:
                print(f"  保存提示 (第{i+1}秒)"); break
            if i in (10, 20):
                try: await ed.click(timeout=3000)
                except: await page.evaluate("()=>{const e=document.querySelector('.ProseMirror');if(e)e.focus();}")
                await asyncio.sleep(0.3)
                await page.keyboard.press("End")
                await page.keyboard.type(" ",delay=50)
                await asyncio.sleep(0.2)
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.3)

        # 验证
        print("验证草稿箱...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        dt = await page.evaluate("()=>document.body.innerText||''")
        sk = title[:8]
        if sk in dt:
            print(f"[SUCCESS] 在草稿箱中!")
        else:
            print(f"[FAIL] 未找到 (页面长度: {len(dt)})")
            print(f"  内容: {dt[:500]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())