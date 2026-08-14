#!/usr/bin/env python3
"""头条草稿箱上传 v9 - 使用 ProseMirror view.dispatch() API + 正确的图片布局

核心改进：
1. 使用来自 upload_visible.py 的正确 calc_image_layout 算法
2. 先上传图片获取服务器URL，再通过 ProseMirror view.dispatch() 一次性设置所有内容
3. 正确处理 image 节点的 data 属性格式
4. 每篇文章独立页面 + 增强遮罩处理
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


# ====== 来自 upload_visible.py 的正确 calc_image_layout ======
def calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局（5张图上限）——均匀分布，避免中间大片文字空档。
    原则：
    - 第1段后固定1张（用掉1张）——记为位置A
    - 剩下的所有图组（每组2张）+ 最后一组位置 = 优先固定在 total_paragraphs - 2
      （保证结尾恰好2段纯文字）
    - 所有配图位置从 A 到 最后一组 之间做等步长均匀分布
    - 若保持结尾2段导致中间"纯文字空档">3段，则尝试放宽结尾为3段换取空档≤3段
      （中间空窗比结尾多1段纯文字更影响阅读体验）
    - 若最后一组之后纯文字<1段（图紧贴最后一行），则删除该组避免结尾贴图
    返回 dict: {段落号: 图片数量}
    """
    if total_paragraphs < 1:
        return {}

    n_groups = (num_images - 1) // 2  # 5张图→2组，3张→1组，3张以下→0组
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}

    first = 1

    def _build_positions(last):
        """给定最后一组位置last，返回均匀分布的positions列表（含first）"""
        if last < 3:
            return [first]
        pos_list = [first]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups:
                    raw = last
                else:
                    raw = first + step * k
                pos = int(round(raw))
                min_pos = pos_list[-1] + 2
                remaining_after = n_groups - k
                max_pos = last - 2 * remaining_after
                pos = max(min_pos, min(max_pos, pos))
                pos_list.append(pos)
        # 结尾贴图修正
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list

    def _max_gap(pos_list):
        """计算相邻配图之间的最大纯文字空档"""
        if len(pos_list) < 2:
            return 0
        return max(pos_list[i+1] - pos_list[i] - 1 for i in range(len(pos_list) - 1))

    # 候选方案：结尾保2段 vs 结尾保3段（3段仅在2段方案空档>3时才考虑）
    candidates = []
    for tail_target in [2, 3]:
        last_cand = total_paragraphs - tail_target
        if last_cand >= 3:
            positions = _build_positions(last_cand)
            if len(positions) >= 2:
                actual_tail = total_paragraphs - positions[-1]
                gap = _max_gap(positions)
                candidates.append((gap, actual_tail, positions))

    if not candidates:
        return {1: 1}

    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)

    candidates.sort(key=_score)
    best_positions = candidates[0][2]

    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


def extract_html_text_and_images(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
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


async def remove_all_overlays(page):
    """激进移除所有遮罩层"""
    await page.evaluate("""
        () => {
            const style = document.createElement('style');
            style.id = 'anti-mask-v9';
            style.textContent = `
                .byte-drawer-mask, .byte-modal-mask, .byte-overlay,
                .byte-drawer-wrapper, .byte-modal-wrapper,
                [class*="drawer-mask"], [class*="modal-mask"],
                [class*="overlay"] { display: none !important; pointer-events: none !important; }
            `;
            document.head.appendChild(style);
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.3)


async def upload_images_one_by_one(page, img_bytes_list):
    """逐张上传图片，获取服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_all_overlays(page)

        # 清空编辑器
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = '<p></p>'; ed.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        """)
        await asyncio.sleep(0.3)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.2)

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
        for _ in range(90):
            await asyncio.sleep(0.5)
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


# ====== ProseMirror view.dispatch() 内容设置 ======
PM_SET_CONTENT_JS = """(function(){
function findView(){
  var editor=document.querySelector('.ProseMirror');
  if(!editor)return null;
  // 通过 pmViewDesc 查找
  var desc=editor.pmViewDesc;
  while(desc){if(desc.view&&desc.view.state)return desc.view;desc=desc.parent;}
  // 通过 React fiber 查找
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
}
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
var urlAttr='src';
var imAttrs={};
if(im){
  var imSpec=schema.nodes[im];
  if(imSpec&&imSpec.spec&&imSpec.spec.attrs){
    Object.keys(imSpec.spec.attrs).forEach(function(an){
      var a=imSpec.spec.attrs[an];
      if(an==='src'||an==='url'||an==='href')urlAttr=an;
      imAttrs[an]=a&&a.default!==undefined?a.default:'[no-default]';
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
          attrs[urlAttr]=imgUrl;
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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length,nodes:nts,pn:pn,in:im,urlAttr:urlAttr,imAttrs:imAttrs});
}catch(e){
  return JSON.stringify({status:'error',error:e.message,nodes:nts,pn:pn,in:im,urlAttr:urlAttr});
}
})()"""


async def set_content_via_pm(page, text_parts, image_urls, image_layout):
    """通过ProseMirror view.dispatch() API设置内容"""
    data_json = json.dumps({"tp": text_parts, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
    await page.evaluate("window._pmData=" + data_json + ";")
    await asyncio.sleep(0.2)

    result = await page.evaluate(PM_SET_CONTENT_JS)
    print(f"  PM dispatch: {result}")

    try:
        data = json.loads(result)
        if data.get('status') == 'ok' and data.get('imgs', 0) > 0:
            return True
    except: pass
    return False


async def process_article(context, art, index, total):
    """处理单篇文章"""
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

    # 使用正确的图片布局算法
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  图片布局: {image_layout}")

    # 创建独立页面
    page = await context.new_page()

    try:
        print(f"  导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

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
        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => {
                    const ed = document.querySelector('.ProseMirror');
                    return ed && ed.getBoundingClientRect().width > 0;
                }
            """)
            if ready:
                print("  [OK] 编辑器就绪")
                break
        else:
            print("  [ERROR] 编辑器未就绪")
            await page.screenshot(path=f"/workspace/v9_art{index}_err.png")
            return False

        # [阶段1] 上传图片获取URL
        image_urls = []
        if img_bytes_list:
            print(f"  [1/3] 上传图片 ({len(img_bytes_list)}张)...")
            image_urls = await upload_images_one_by_one(page, img_bytes_list)
            valid = len([u for u in image_urls if u])
            print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

        # [阶段2] 通过ProseMirror API设置内容
        print(f"  [2/3] 设置内容 (ProseMirror dispatch)...")
        pm_ok = False
        try:
            pm_ok = await set_content_via_pm(page, paragraphs, image_urls, image_layout)
        except Exception as e:
            print(f"  [WARN] PM dispatch 异常: {e}")
        if not pm_ok:
            print("  [WARN] ProseMirror dispatch 失败，回退到键盘输入")
            # 回退方案：键盘逐段输入
            await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }
            """)
            await asyncio.sleep(0.3)
            img_idx = 0
            valid_urls = [u for u in image_urls if u]
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
                            await page.evaluate(f"""
                                () => {{
                                    const ed = document.querySelector('.ProseMirror');
                                    if (!ed) return;
                                    ed.focus();
                                    const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                                    const cd = {{
                                        types: ['text/html'],
                                        getData: function(type) {{ return type === 'text/html' ? '<img src="{valid_urls[img_idx]}" />' : ''; }},
                                        setData: function() {{}}, clearData: function() {{}}, files: [], items: []
                                    }};
                                    Object.defineProperty(ev, 'clipboardData', {{value: cd}});
                                    ed.dispatchEvent(ev);
                                }}
                            """)
                            await asyncio.sleep(0.3)
                            await page.keyboard.press('Enter')
                            await asyncio.sleep(0.1)
                            img_idx += 1

        # [阶段3] 填写标题
        print(f"  [3/3] 填写标题...")
        await remove_all_overlays(page)
        title_set = await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (!el) return 'not_found';
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, {json.dumps(title)});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
                return el.value;
            }}
        """)
        print(f"  标题设置: {title_set[:30] if title_set else 'FAIL'}...")
        await asyncio.sleep(3)

        # 触发编辑器事件 + 小编辑触发自动保存
        print(f"  触发自动保存...")
        await remove_all_overlays(page)
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) {
                    ed.focus();
                    ed.dispatchEvent(new Event('input', {bubbles: true}));
                    ed.dispatchEvent(new Event('change', {bubbles: true}));
                    ed.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(1)
        # 在编辑器中做一个小编辑来触发自动保存
        # 使用 ProseMirror transaction 做无痕编辑
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return;
                // 通过 React fiber 找到 view
                function findView() {
                    var desc = ed.pmViewDesc;
                    while (desc) { if (desc.view && desc.view.state) return desc.view; desc = desc.parent; }
                    function sf(fiber, v) {
                        if (!fiber || v.has(fiber) || v.size > 500) return null;
                        v.add(fiber);
                        if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
                        if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
                        if (fiber.memoizedState) { var s = fiber.memoizedState; while (s) { if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view; s = s.next; } }
                        var r = sf(fiber.child, v); if (r) return r;
                        return sf(fiber.sibling, v);
                    }
                    var el = ed;
                    for (var i = 0; i < 15 && el; i++) {
                        var fk = Object.keys(el).find(function(k) { return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0; });
                        if (fk) { var v = new Set(); var r = sf(el[fk], v); if (r) return r; }
                        el = el.parentElement;
                    }
                    return null;
                }
                var view = findView();
                if (!view) return;
                // 在文档末尾插入一个空格再删除，触发 change 事件
                var docSize = view.state.doc.content.size;
                var tr = view.state.tr;
                var schema = view.state.schema;
                // 插入空格
                tr.insert(docSize, schema.text(' '));
                view.dispatch(tr);
                // 立即删除
                var tr2 = view.state.tr;
                tr2.delete(docSize, docSize + 1);
                view.dispatch(tr2);
            }
        """)
        await asyncio.sleep(3)

        # 额外：点击编辑器触发 focus 事件
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.focus(); ed.click(); } }")
        await asyncio.sleep(1)

        # 等待自动保存
        print(f"  等待自动保存...")
        saved = False
        for i in range(60):
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

        if not saved:
            print(f"  未检测到保存，手动触发...")
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
                    () => { return document.body.innerText.indexOf('草稿已保存') !== -1; }
                """)
                if result:
                    print(f"  [{i+1}s] 保存成功!")
                    saved = True
                    break

        await page.screenshot(path=f"/workspace/v9_art{index}.png")
        return saved

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        await page.screenshot(path=f"/workspace/v9_art{index}_err.png")
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:30]}... {len(paragraphs)}段 {len(images)}图 布局={layout}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        # 验证登录
        print("\n验证登录...")
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
                if await process_article(context, art, i, len(articles)):
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

        await page.screenshot(path="/workspace/draft_v9_final.png")
        await page.close()
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())