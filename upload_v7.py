#!/usr/bin/env python3
"""v7: 修复PM API findView + 完整上传
关键修复: 通过React root container (#root) 查找ProseMirror view
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
LOG_FILE = os.path.join(BASE_DIR, "upload_v7.log")

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

# ---- 修复后的findView: 通过React root container查找 ----
PM_SET_CONTENT_JS = """(function(){
// 通过React root查找ProseMirror view
function findView(){
  var rootEl=document.querySelector('#root');
  if(!rootEl)return null;
  var rk=Object.keys(rootEl).find(function(k){return k.indexOf('__reactContainer')===0;});
  if(!rk||!rootEl[rk])return null;
  
  function sf(fiber,depth){
    if(!fiber||depth>50)return null;
    if(fiber.memoizedState){
      var s=fiber.memoizedState;
      while(s){
        if(s.memoizedState&&s.memoizedState.view&&s.memoizedState.view.state)return s.memoizedState.view;
        s=s.next;
      }
    }
    var r=sf(fiber.child,depth+1);
    if(r)return r;
    return sf(fiber.sibling,depth+1);
  }
  return sf(rootEl[rk],0);
}

var view=findView();
if(!view)return JSON.stringify({status:'no_view'});

var schema=view.state.schema;
var nts=Object.keys(schema.nodes);
var pn='paragraph',im='image',dn='doc';

// 从schema确认节点名
nts.forEach(function(k){
  if(k==='paragraph'||k==='para')pn=k;
  if(k==='doc')dn=k;
  if(k==='image'||k==='imageUpload'||k==='media'||k==='img')im=k;
});
if(!im)nts.forEach(function(k){if(k.toLowerCase().indexOf('image')>=0||k.toLowerCase().indexOf('media')>=0)im=k;});
if(!pn)nts.forEach(function(k){if(k.toLowerCase().indexOf('para')>=0)pn=k;});
if(!dn)nts.forEach(function(k){if(k==='doc'||k==='document'||k==='article')dn=k;});
if(!pn||!dn)return JSON.stringify({status:'no_types',nodes:nts});

var data=window._pmData;
var content=[];
var ui=0;

// image节点使用 data.url 属性
var imSpec=schema.nodes[im];
var useDataAttr=false;
if(imSpec&&imSpec.spec&&imSpec.spec.attrs){
  var attrs=imSpec.spec.attrs;
  useDataAttr=!!attrs.data;
}

for(var i=0;i<data.tp.length;i++){
  if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
  var t=i+1;
  if(data.il[t]){
    for(var j=0;j<data.il[t];j++){
      if(ui<data.iu.length&&data.iu[ui]){
        var imgUrl=data.iu[ui];
        var imgAttrs={};
        if(useDataAttr){
          imgAttrs.data={url:imgUrl,icUri:imgUrl,catchErrorUrl:"",link:"",caption:"图片来源于网络",ic:false,naturalHeight:0,naturalWidth:0,srcType:"",captionLenErr:false,needCheck:false};
        }else{
          imgAttrs.src=imgUrl;
          imgAttrs.alt='图片来源于网络';
        }
        content.push({type:im,attrs:imgAttrs});
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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length,useDataAttr:useDataAttr});
}catch(e){
  return JSON.stringify({status:'error',error:e.message});
}
})()"""

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
    
    image_layout = calc_image_layout(len(paragraphs), len(images_base64))
    log(f"  图片布局: {image_layout}")
    
    page = await context.new_page()
    
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
        
        # [2] 清空旧内容
        has_old = await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                return editor && editor.textContent.trim().length > 10;
            }
        """)
        if has_old:
            log(f"  清空旧内容...")
            await dismiss_popups(page)
            await asyncio.sleep(1)
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) editor.innerHTML = '<p><br></p>';
                }
            """)
            await asyncio.sleep(1)
        
        # [3] 填标题
        log(f"  [3] 填标题: {title}")
        await page.evaluate("""
            (t) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, t);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
            }
        """, title)
        await asyncio.sleep(2)
        
        # [4] 逐张上传图片，获取服务器URL
        log(f"  [4] 上传{len(images_base64)}张图片...")
        image_urls = []
        
        for img_idx, data_url in enumerate(images_base64):
            img_bytes = compress_image(data_url)
            if not img_bytes:
                image_urls.append("")
                continue
            
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.innerHTML = '<p><br></p>';
                        editor.focus();
                    }
                }
            """)
            await asyncio.sleep(0.3)
            
            img_b64 = base64.b64encode(img_bytes).decode('ascii')
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
            """, img_b64)
            
            img_url = ""
            for wait_i in range(90):
                img_url = await page.evaluate("""
                    () => {
                        const imgs = document.querySelectorAll('.ProseMirror img');
                        if (imgs.length === 0) return '';
                        return imgs[imgs.length - 1].src || '';
                    }
                """)
                if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                    break
                await asyncio.sleep(1)
            
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                image_urls.append(img_url)
                log(f"    图片{img_idx+1}: OK")
            else:
                image_urls.append("")
                log(f"    图片{img_idx+1}: FAIL")
        
        valid_urls = [u for u in image_urls if u]
        log(f"  [4] 完成: {len(valid_urls)}/{len(images_base64)}张已上传")
        
        if not valid_urls:
            log(f"  [ERROR] 没有成功上传的图片")
            await page.close()
            return False
        
        # [5] 设置ProseMirror内容（使用修复后的findView）
        log(f"  [5] 设置ProseMirror完整内容...")
        
        data_json = json.dumps({
            "tp": paragraphs,
            "iu": image_urls,
            "il": image_layout
        }, ensure_ascii=False)
        
        await page.evaluate("window._pmData=" + data_json + ";")
        pm_result = await page.evaluate(PM_SET_CONTENT_JS)
        
        log(f"  PM API: {pm_result[:200]}")
        
        pm_data = None
        try:
            pm_data = json.loads(pm_result) if pm_result else None
        except:
            pass
        
        if pm_data and pm_data.get('status') == 'ok':
            log(f"  [OK] PM设置成功: {pm_data.get('imgs',0)}张, {pm_data.get('chars',0)}字")
        else:
            log(f"  [ERROR] PM设置失败")
            await page.close()
            return False
        
        await asyncio.sleep(2)
        
        # [6] 触发保存
        log(f"  [6] 触发保存...")
        
        # 修改标题触发自动保存
        await page.evaluate("""
            (t) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, t + ' ');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                setTimeout(() => {
                    ns.call(el, t);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.blur();
                }, 500);
            }
        """, title)
        
        # 等待保存
        await asyncio.sleep(3)
        
        # 点击预览按钮触发额外保存
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
        
        # 关闭预览弹窗
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
        
        # [7] 验证
        log(f"  [7] 验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(5)
        
        draft_html = await page.evaluate("() => document.body.innerText")
        found = title[:15] in draft_html
        
        if found:
            log(f"  [SUCCESS] 文章已在草稿箱中!")
            await page.close()
            return True
        else:
            log(f"  [FAIL] 未在草稿箱中找到文章")
            log(f"    草稿箱前300字: {draft_html[:300]}")
            await page.close()
            return False
            
    except Exception as e:
        log(f"  [ERROR] {e}")
        try:
            await page.close()
        except:
            pass
        return False

async def main():
    log("=" * 60)
    log(f"头条草稿箱上传 v7 - 修复PM API")
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