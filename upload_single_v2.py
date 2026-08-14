#!/usr/bin/env python3
"""单篇上传 - 先获取新pgc_id再编辑"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

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

async def get_new_pgc_id(page):
    """获取新的pgc_id"""
    # 拦截article/new响应
    new_pgc_id = None
    
    async def handle_response(response):
        nonlocal new_pgc_id
        if 'article/new' in response.url and response.status == 200:
            try:
                data = await response.json()
                pgc_id = data.get('data', {}).get('pgc_id') or data.get('pgc_id')
                if pgc_id:
                    new_pgc_id = str(pgc_id)
                    print(f"  [NEW] pgc_id={new_pgc_id}")
            except: pass
    
    page.on('response', handle_response)
    
    # 导航到发布页面触发article/new
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)
    
    return new_pgc_id

async def main():
    import sys
    article_index = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    art = articles[article_index - 1]
    title = art["title"]
    html_path = art["html_file"]
    cover_files = art.get("cover_files", [])

    print(f"文章: [{article_index}] {title}")
    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"内容: {len(paragraphs)}段, {len(images)}张图")

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"布局: {image_layout}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        await context.add_cookies([{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()])

        page = await context.new_page()
        
        # 网络监控
        save_requests = []
        async def handle_response(response):
            url = response.url
            if any(kw in url for kw in ['save', 'draft', 'auto_save', 'article/new', 'article/edit', 'article/publish']):
                try:
                    body = await response.text()
                    summary = body[:300] if len(body) < 2000 else body[:300] + '...'
                    save_requests.append(f"{response.status} {response.request.method} {url[:120]}\n    {summary}")
                except: pass
        page.on('response', handle_response)

        # 获取新pgc_id
        print("获取新pgc_id...")
        new_pgc_id = await get_new_pgc_id(page)
        
        if not new_pgc_id:
            print("  [ERROR] 无法获取新pgc_id")
            for req in save_requests:
                print(f"  {req}")
            await browser.close()
            return
        
        # 关闭弹窗
        await page.evaluate("""
            () => {
                document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
                const style = document.createElement('style');
                style.textContent = '.byte-drawer-mask, .byte-modal-mask, .byte-overlay { display: none !important; }';
                document.head.appendChild(style);
            }
        """)
        await asyncio.sleep(1)
        for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
            try:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=1500): await btn.click(); await asyncio.sleep(0.5)
            except: pass

        # 等待编辑器
        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }")
            if ready: break
        print("编辑器就绪")

        # 上传图片
        image_urls = []
        for idx, img_bytes in enumerate(img_bytes_list):
            print(f"  上传图片{idx+1}/{len(img_bytes_list)}...", end=" ", flush=True)
            await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = '<p></p>'; ed.focus(); } }
            """)
            await asyncio.sleep(0.3)

            b64 = base64.b64encode(img_bytes).decode('ascii')
            await page.evaluate(f"""
                () => {{
                    const ed = document.querySelector('.ProseMirror'); if (!ed) return;
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
            url = ""
            for _ in range(60):
                await asyncio.sleep(0.5)
                url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
                if url and not url.startswith('blob:') and not url.startswith('data:'): break
            ok = bool(url and not url.startswith('blob:') and not url.startswith('data:'))
            print("OK" if ok else "FAIL")
            image_urls.append(url if ok else "")
            await asyncio.sleep(0.3)

        valid_urls = [u for u in image_urls if u]
        print(f"图片上传: {len(valid_urls)}/{len(img_bytes_list)}张成功")

        # 清除编辑器残留
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { while (ed.firstChild) ed.removeChild(ed.firstChild); ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        # 通过PM API设置内容
        data_json = json.dumps({"tp": paragraphs, "iu": valid_urls, "il": image_layout}, ensure_ascii=False)
        await page.evaluate("window._pmData=" + data_json + ";")

        pm_result = await page.evaluate("""(function(){
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
var imAttrs={};
if(im){
  var imSpec=schema.nodes[im];
  if(imSpec&&imSpec.spec&&imSpec.spec.attrs){
    Object.keys(imSpec.spec.attrs).forEach(function(an){
      var a=imSpec.spec.attrs[an];
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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length});
}catch(e){
  return JSON.stringify({status:'error',error:e.message});
}
})()""")
        print(f"PM API: {pm_result}")

        try:
            pm_data = json.loads(pm_result)
            if pm_data.get('status') == 'ok':
                print(f"  [OK] PM: {pm_data.get('chars')}字, {pm_data.get('imgs')}张图")
        except: pass

        # 填写标题
        title_json = json.dumps(title)
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                         document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, {title_json});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }}
        """)
        print("标题已填写")

        # 触发保存
        await asyncio.sleep(3)
        print("触发保存...")
        try:
            title_el = page.locator('textarea[placeholder*="文章标题"]').first
            await title_el.click(timeout=3000)
            await asyncio.sleep(0.5)
            await title_el.press('Space')
            await asyncio.sleep(0.5)
            await title_el.press('Backspace')
            await asyncio.sleep(0.5)
            await title_el.blur()
        except: pass

        # 等待保存
        print("等待保存...")
        saved = False
        for i in range(60):
            await asyncio.sleep(1)
            saved = await page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1;
                }
            """)
            if saved:
                print(f"  [OK] 保存成功 (第{i+1}秒)")
                break
            if i % 10 == 9:
                print(f"  等待中... ({i+1}秒)")

        if not saved:
            print("  [WARN] 未检测到保存")

        # 打印网络请求
        print("\n网络请求摘要:")
        for req in save_requests:
            print(f"  {req}")

        await page.screenshot(path=f"/workspace/v2_art{article_index}.png")
        await browser.close()
        print(f"完成")

if __name__ == "__main__":
    asyncio.run(main())