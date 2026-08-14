#!/usr/bin/env python3
"""v16: 修复PM状态同步 + 图片去重 + 每篇文章独立页面

核心修复：
1. 上传图片后用PM API清空编辑器（而非DOM操作）
2. 确保PM状态和DOM一致
3. 每篇文章用带时间戳的URL打开独立发布页
4. 增强封面图上传
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
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1): pos_list.pop()
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
    for i, p in enumerate(best_positions): layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


def extract_html_text_and_images(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs, images = [], []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text: paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
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


async def remove_overlays(page):
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper, [class*="drawer-mask"], [class*="modal-mask"]').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.3)


async def dismiss_notifications(page):
    await remove_overlays(page)
    for btn_text in ["关闭", "不恢复", "知道了", "确定", "取消"]:
        try:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                await asyncio.sleep(0.3)
        except: pass


# ---- PM API 工具函数 (内联findView避免Python字符串冲突) ----

FIND_VIEW_BODY = '''
function findView(){
  var editor=document.querySelector('.ProseMirror');
  if(!editor)return null;
  var desc=editor.pmViewDesc;
  while(desc){if(desc.view&&desc.view.state)return desc.view;desc=desc.parent;}
  function sf(fiber,v){
    if(!fiber||v.has(fiber)||v.size>500)return null;
    v.add(fiber);
    if(fiber.stateNode&&fiber.stateNode.view&&fiber.stateNode.view.state)return fiber.stateNode.view;
    if(fiber.memoizedProps&&fiber.memoizedProps.view&&fiber.memoizedProps.view.state)return fiber.memoizedProps.view;
    if(fiber.memoizedState){var s=fiber.memoizedState;while(s){if(s.memoizedState&&s.memoizedState.view&&s.memoizedState.view.state)return s.memoizedState.view;s=s.next;}}
    var r=sf(fiber.child,v);if(r)return r;
    return sf(fiber.sibling,v);
  }
  var el=editor;
  for(var i=0;i<15&&el;i++){
    var fk=Object.keys(el).find(function(k){return k.indexOf('__reactFiber')===0||k.indexOf('__reactInternalInstance')===0;});
    if(fk){var v=new Set();var r=sf(el[fk],v);if(r)return r;}
    el=el.parentElement;
  }
  return null;
}'''


async def clear_editor_via_pm(page):
    """通过PM API清空编辑器（保持状态同步）"""
    js = FIND_VIEW_BODY + '''
var view=findView();
if(!view)return 'no_view';
var schema=view.state.schema;
var emptyDoc=schema.nodes.doc.createAndFill();
var tr=view.state.tr;
tr.replaceWith(0,view.state.doc.content.size,emptyDoc.content);
view.dispatch(tr);
return 'ok';'''
    return await page.evaluate(js)


async def set_content_via_pm_api(page, text_paragraphs, image_urls, image_layout):
    """通过PM API一次性设置完整内容（文字+图片）"""
    data_json = json.dumps({"tp": text_paragraphs, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
    await page.evaluate("window._pmData=" + data_json + ";")

    js = FIND_VIEW_BODY + '''
var view=findView();
if(!view)return JSON.stringify({status:'no_view'});
var schema=view.state.schema;
var nts=Object.keys(schema.nodes);
var pn=null,im=null,dn=null;
nts.forEach(function(k){
  if(k==='paragraph'||k==='para')pn=k;
  if(k==='doc')dn=k;
  if(k==='image'||k==='imageUpload'||k==='media'||k==='img')im=k;
});
if(!im)nts.forEach(function(k){if(k.toLowerCase().indexOf('image')>=0||k.toLowerCase().indexOf('media')>=0)im=k;});
if(!pn)nts.forEach(function(k){if(k.toLowerCase().indexOf('para')>=0)pn=k;});
if(!dn)nts.forEach(function(k){if(k==='doc'||k==='document'||k==='article')dn=k;});
if(!pn||!dn)return JSON.stringify({status:'no_types',nodes:nts});
var imAttrs={};
if(im){
  var imSpec=schema.nodes[im];
  if(imSpec&&imSpec.spec&&imSpec.spec.attrs){
    Object.keys(imSpec.spec.attrs).forEach(function(an){
      imAttrs[an]=imSpec.spec.attrs[an]&&imSpec.spec.attrs[an].default!==undefined?imSpec.spec.attrs[an].default:'[no-default]';
    });
  }
}
var data=window._pmData;
var content=[];
var ui=0;
var hasDataAttr=imAttrs&&Object.keys(imAttrs).indexOf('data')>=0;
for(var i=0;i<data.tp.length;i++){
  if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
  var t=i+1;
  if(data.il[t]){
    for(var j=0;j<data.il[t];j++){
      if(ui<data.iu.length&&data.iu[ui]){
        var imgUrl=data.iu[ui];
        var attrs={};
        if(hasDataAttr){
          attrs.data={url:imgUrl,icUri:imgUrl,catchErrorUrl:"",link:"",caption:"图片来源于网络",ic:false,naturalHeight:0,naturalWidth:0,srcType:"",captionLenErr:false,needCheck:false};
        }else{
          attrs.src=imgUrl;
          attrs.alt='图片来源于网络';
        }
        content.push({type:im,attrs:attrs});
        ui++;
      }
    }
  }
}
try{
  var doc=schema.nodeFromJSON({type:dn,content:content});
  view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
  var ic=0;
  view.state.doc.descendants(function(node){if(node.type.name===im)ic++;return true;});
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length,hasDataAttr:hasDataAttr});
}catch(e){
  return JSON.stringify({status:'error',error:e.message});
}'''
    return await page.evaluate(js)


async def upload_images_to_server(page, img_bytes_list):
    """逐张上传图片到服务器，返回URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)

        # 用PM API清空编辑器
        await clear_editor_via_pm(page)
        await asyncio.sleep(0.3)

        # 通过paste事件上传
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
        for wait_i in range(60):
            await asyncio.sleep(0.5)
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

        await asyncio.sleep(0.3)

    return image_urls


async def fill_title(page, title):
    title_json = json.dumps(title)
    result = await page.evaluate(f"""
        () => {{
            const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                     document.querySelector('textarea[placeholder*="请输入文章标题"]');
            if (!el) return 'not_found';
            el.focus();
            const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            ns.call(el, {title_json});
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
            return el.value;
        }}
    """)
    return result


async def upload_cover(page, cover_paths):
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("    无有效封面图，跳过")
        return False

    print(f"    上传{len(valid)}张封面...")

    # 滚动到顶部
    await page.evaluate("window.scrollTo(0, 0);")
    await asyncio.sleep(1)

    # 选择3图模式
    await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if (r.value === '3') {
                    r.click();
                    r.dispatchEvent(new Event('change', {bubbles: true}));
                    return;
                }
            }
        }
    """)
    await asyncio.sleep(2)

    for ci, cf in enumerate(valid):
        print(f"      封面{ci+1}: {os.path.basename(cf)}...", end=" ", flush=True)

        # 点击添加按钮
        try:
            add_btn = page.locator('.article-cover-add').first
            await add_btn.scroll_into_view_if_needed()
            await add_btn.click()
            await asyncio.sleep(1.5)
        except:
            await page.evaluate("""
                () => {
                    const add = document.querySelector('.article-cover-add');
                    if (add) {
                        add.scrollIntoView({block: 'center'});
                        add.click();
                    }
                }
            """)
            await asyncio.sleep(1.5)

        # 上传文件
        uploaded = False
        try:
            # 方法1: 找可见的file input
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(cf, timeout=5000)
            await asyncio.sleep(2)
            uploaded = True
        except:
            try:
                # 方法2: 通过file chooser
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await page.evaluate("""
                        () => {
                            const add = document.querySelector('.article-cover-add');
                            if (add) add.click();
                        }
                    """)
                file_chooser = await fc_info.value
                await file_chooser.set_files(cf)
                await asyncio.sleep(2)
                uploaded = True
            except:
                pass

        print("OK" if uploaded else "FAIL")

    return True


async def wait_for_save(page, timeout=30):
    for i in range(timeout):
        await asyncio.sleep(1)
        saved = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                const btns = document.querySelectorAll('button, span');
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if (t.indexOf('草稿已保存') !== -1) return true;
                }
                return false;
            }
        """)
        if saved: return True
    return False


async def trigger_save(page):
    """触发保存：点击标题框再blur"""
    try:
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(timeout=3000)
        await asyncio.sleep(0.3)
        await title_el.press('Space')
        await asyncio.sleep(0.3)
        await title_el.press('Backspace')
        await asyncio.sleep(0.5)
        await title_el.blur()
        return True
    except:
        return False


async def process_article(context, art, index, total):
    title = art["title"]
    html_path = art["html_file"]
    cover_files = art.get("cover_files", [])

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  内容: {len(paragraphs)}段文字, {len(images)}张图片")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    print(f"  压缩: {len(img_bytes_list)}/{len(images)}张有效")

    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")

    page = await context.new_page()

    try:
        # [1] 打开发布页面（带时间戳避免缓存）
        ts = int(time.time() * 1000)
        print(f"  [1] 打开发布页面...")
        await page.goto(f"{PUBLISH_URL}?_t={ts}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_notifications(page)

        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }
            """)
            if ready: break
        else:
            print("  [ERROR] 编辑器未就绪")
            return False
        print("  [OK] 编辑器就绪")

        # [2] 上传图片到服务器
        image_urls = []
        if img_bytes_list:
            print(f"  [2] 上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_to_server(page, img_bytes_list)
            valid_count = len([u for u in image_urls if u])
            print(f"  结果: {valid_count}/{len(img_bytes_list)}张成功")
        valid_urls = [u for u in image_urls if u]

        # [3] 用PM API清空编辑器（关键修复：确保PM状态干净）
        print(f"  [3] 清空编辑器(PM API)...")
        clear_result = await clear_editor_via_pm(page)
        print(f"  清空: {clear_result}")
        await asyncio.sleep(0.5)

        # [4] 通过PM API设置完整内容
        print(f"  [4] 设置内容 ({len(paragraphs)}段, {len(valid_urls)}张图)...")
        pm_result = await set_content_via_pm_api(page, paragraphs, valid_urls, image_layout)
        print(f"  PM: {pm_result[:200]}")

        try:
            pm_data = json.loads(pm_result)
            if pm_data.get('status') == 'ok':
                pm_imgs = pm_data.get('imgs', 0)
                pm_chars = pm_data.get('chars', 0)
                print(f"  [OK] PM: {pm_chars}字, {pm_imgs}张图片")
            else:
                print(f"  [WARN] PM失败: {pm_result[:100]}")
        except:
            print(f"  [WARN] 无法解析PM结果")

        await asyncio.sleep(2)

        # 验证DOM图片数
        dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
        dom_chars = await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); return ed ? ed.innerText.length : 0; }")
        print(f"  DOM: {dom_chars}字, {dom_imgs}张图片")

        if dom_imgs != len(valid_urls):
            print(f"  [WARN] DOM图片数({dom_imgs}) != 预期({len(valid_urls)})，可能重复")

        # [5] 填写标题
        print(f"  [5] 填写标题...")
        title_result = await fill_title(page, title)
        print(f"  标题: {title_result}")
        await asyncio.sleep(3)

        # 触发保存
        print(f"  触发保存...")
        await trigger_save(page)
        saved = await wait_for_save(page, timeout=30)
        if saved:
            print(f"  [OK] 自动保存成功")
        else:
            print(f"  [WARN] 未检测到保存提示，尝试预览触发...")
            try:
                preview_btn = page.locator("text=预览").first
                if await preview_btn.is_visible(timeout=3000):
                    await preview_btn.click()
                    await asyncio.sleep(5)
                    # 关闭预览窗口
                    for p in context.pages:
                        if p != page:
                            await p.close()
                            await asyncio.sleep(1)
                    print(f"  已通过预览触发保存")
                    await asyncio.sleep(3)
            except:
                print(f"  预览按钮不可用，等待更长时间...")
                await asyncio.sleep(15)

        # [6] 上传封面
        print(f"  [6] 上传封面...")
        await upload_cover(page, cover_files)

        # 最终保存
        await trigger_save(page)
        await wait_for_save(page, timeout=15)

        await page.screenshot(path=f"/workspace/v16_art{index}.png")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v16_art{index}_err.png")
        except: pass
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章\n")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:35]}... | {len(paragraphs)}段 {len(images)}图 | 布局={layout}")

    print(f"\n启动浏览器...")
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
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        print("验证登录...")
        test_page = await context.new_page()
        await test_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await test_page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await test_page.close()

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                if await process_article(context, art, i, len(articles)):
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [FATAL] {e}")
                traceback.print_exc()
            await asyncio.sleep(3)

        # 验证草稿箱
        print(f"\n{'='*60}")
        print("验证草稿箱...")
        verify_page = await context.new_page()
        await verify_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await verify_page.evaluate("() => document.body.innerText.substring(0, 8000)")

        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:45]}")

        print(f"\n草稿箱内容片段:")
        for line in draft_text.split('\n')[:30]:
            line = line.strip()
            if line and len(line) > 5:
                print(f"    {line[:120]}")

        await verify_page.screenshot(path="/workspace/v16_draft_final.png")
        await verify_page.close()
        await browser.close()

    print(f"\n上传完成: {success}/{len(articles)} 篇成功")


if __name__ == "__main__":
    asyncio.run(main())