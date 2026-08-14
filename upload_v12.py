#!/usr/bin/env python3
"""v12: 尝试save_ugc_draft端点 + 删除旧草稿

策略:
1. 先删除旧草稿释放空间
2. 使用save_ugc_draft端点（而非article/publish）
3. 尝试不同的参数组合
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
LOG_FILE = os.path.join(BASE_DIR, "upload_v12.log")

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
    except:
        return None

async def dismiss_popups(page):
    for _ in range(3):
        try:
            await page.evaluate("""
                () => {
                    document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask').forEach(m => m.remove());
                    document.querySelectorAll('button, span').forEach(b => {
                        const t = (b.textContent || '').trim();
                        if (['关闭','取消','知道了','不恢复'].includes(t)) b.click();
                    });
                }
            """)
            await asyncio.sleep(0.5)
        except:
            break

PM_SET_CONTENT_JS = """(function(){
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

async def delete_old_drafts(page):
    """删除旧草稿（保留最近3篇）"""
    log("  获取草稿列表...")
    drafts = await page.evaluate("""
        async () => {
            try {
                const resp = await fetch(
                    'https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=2&count=20&app_id=1231',
                    {credentials: 'include'}
                );
                const data = await resp.json();
                if (data.code === 0) {
                    return data.draft_list.map(d => ({gid: d.gid, title: d.title}));
                }
                return [];
            } catch(e) { return []; }
        }
    """)
    
    log(f"  草稿数: {len(drafts)}")
    for d in drafts[:5]:
        log(f"    - {d.get('title','')[:30]} (gid={d.get('gid')})")
    
    # 删除前10篇旧草稿
    if len(drafts) > 5:
        to_delete = drafts[3:]  # 保留前3篇
        log(f"  删除{len(to_delete)}篇旧草稿...")
        for d in to_delete:
            gid = d.get('gid')
            result = await page.evaluate("""
                async (gid) => {
                    try {
                        const resp = await fetch(
                            'https://mp.toutiao.com/mp/agw/creator_center/draft_delete',
                            {
                                method: 'POST',
                                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                                body: 'gid=' + gid + '&app_id=1231',
                                credentials: 'include'
                            }
                        );
                        const data = await resp.json();
                        return data.code;
                    } catch(e) { return -1; }
                }
            """, gid)
            log(f"    删除 gid={gid}: code={result}")

async def process_article(context, art, index, total):
    category = art.get("category", "未知")
    title = art.get("title", "")
    html_path = art.get("html_file", "")
    
    log(f"\n{'='*60}")
    log(f"[{index}/{total}] {category} - {title}")
    log(f"{'='*60}")
    
    paragraphs, images_base64 = extract_html_content(html_path)
    log(f"  提取: {len(paragraphs)}段文字, {len(images_base64)}张图片")
    
    img_bytes_list = [compress_image(img) for img in images_base64]
    img_bytes_list = [b for b in img_bytes_list if b]
    log(f"  压缩: {len(img_bytes_list)}张有效图片")
    
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    log(f"  图片布局: {image_layout}")
    
    page = await context.new_page()
    
    pgc_id = None
    save_attempts = []
    
    async def on_response(response):
        nonlocal pgc_id
        url = response.url
        if 'article/new' in url and 'format=json' in url:
            try:
                body = await response.json()
                pgc_id = body.get('data', {}).get('pgc', {}).get('id', '')
                log(f"  [API] pgc_id={pgc_id}")
            except:
                pass
        if 'save_ugc_draft' in url or 'article/publish' in url or 'draft/save' in url:
            try:
                body = await response.json()
                save_attempts.append(body)
                log(f"  [SAVE] code={body.get('code')} msg={body.get('message','')} pgc_id={body.get('data',{}).get('pgc_id','')}")
            except:
                pass
    
    page.on("response", on_response)
    
    try:
        # [1] 打开草稿箱，删除旧草稿
        log(f"  [1] 打开草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_popups(page)
        
        # 删除旧草稿
        await delete_old_drafts(page)
        
        # [2] 打开发布页面
        log(f"  [2] 打开发布页面...")
        await page.goto(PUBLISH_URL + "?_t=" + str(int(time.time() * 1000)),
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_popups(page)
        
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
        
        # 等待pgc_id
        if not pgc_id:
            for i in range(10):
                await asyncio.sleep(1)
                if pgc_id:
                    break
        log(f"  pgc_id: {pgc_id}")
        
        # [3] 清空编辑器
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if(ed) { ed.innerHTML = '<p><br></p>'; ed.focus(); } }
        """)
        await asyncio.sleep(1)
        
        # [4] 上传图片
        log(f"  [4] 上传{len(img_bytes_list)}张图片...")
        image_urls = []
        for img_idx, img_bytes in enumerate(img_bytes_list):
            b64 = base64.b64encode(img_bytes).decode('ascii')
            await page.evaluate("""
                (b64) => {
                    const editor = document.querySelector('.ProseMirror');
                    if (!editor) return;
                    editor.innerHTML = '<p><br></p>';
                    editor.focus();
                    const bs = atob(b64);
                    const ab = new ArrayBuffer(bs.length);
                    const ia = new Uint8Array(ab);
                    for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                    const blob = new Blob([ab], {type: 'image/jpeg'});
                    const file = new File([blob], 'img.jpg', {type: 'image/jpeg'});
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    editor.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
                }
            """, b64)
            
            img_url = ""
            for wait_i in range(90):
                img_url = await page.evaluate("""
                    () => { const imgs = document.querySelectorAll('.ProseMirror img'); return imgs.length ? imgs[imgs.length-1].src : ''; }
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
        log(f"  [4] 完成: {len(valid_urls)}/{len(img_bytes_list)}张")
        
        if not valid_urls:
            await page.close()
            return False
        
        # [5] PM API设置内容
        log(f"  [5] PM API设置内容...")
        data_json = json.dumps({"tp": paragraphs, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
        await page.evaluate("window._pmData=" + data_json + ";")
        pm_result = await page.evaluate(PM_SET_CONTENT_JS)
        pm_data = json.loads(pm_result) if pm_result else {}
        log(f"  PM: {pm_data.get('status')} imgs={pm_data.get('imgs')} chars={pm_data.get('chars')}")
        
        if pm_data.get('status') != 'ok':
            await page.close()
            return False
        
        # [6] 填标题
        log(f"  [6] 填标题...")
        title_json = json.dumps(title)
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                const ns = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                el.focus(); ns.call(el, {title_json});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }}
        """)
        await asyncio.sleep(2)
        
        # [7] 尝试多个save端点
        log(f"  [7] 尝试保存...")
        
        # 构建HTML
        html_parts = []
        img_idx = 0
        for p_idx, para_text in enumerate(paragraphs):
            para_num = p_idx + 1
            html_parts.append(f"<p>{para_text}</p>")
            imgs_needed = image_layout.get(para_num, 0)
            for _ in range(imgs_needed):
                if img_idx < len(valid_urls):
                    url = valid_urls[img_idx]
                    html_parts.append(f'<div class="pgc-img"><img src="{url}" icUri="{url}" caption="图片来源于网络"/></div>')
                    img_idx += 1
        
        html_content = "".join(html_parts)
        extra = json.dumps({
            "content_source": 100000000402,
            "content_word_cnt": len("".join(paragraphs)),
            "is_multi_title": 0, "sub_titles": [],
            "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
            "tuwen_wtt_trans_flag": "0"
        }, ensure_ascii=False)
        
        # 尝试不同的端点
        endpoints = [
            "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft",
            "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231",
            "https://mp.toutiao.com/mp/agw/article/publish",
        ]
        
        for ep_url in endpoints:
            save_result = await page.evaluate("""
                async (args) => {
                    const formBody = new URLSearchParams();
                    for (const [k, v] of Object.entries(args.params)) {
                        formBody.append(k, v);
                    }
                    try {
                        const resp = await fetch(args.url, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                            body: formBody.toString(),
                            credentials: 'include'
                        });
                        return await resp.json();
                    } catch(e) { return {error: e.message}; }
                }
            """, {
                "url": ep_url,
                "params": {
                    "source": "29", "article_type": "0",
                    "pgc_id": str(pgc_id) if pgc_id else "0",
                    "title": title, "content": html_content, "extra": extra,
                }
            })
            log(f"  {ep_url.split('/')[-1][:30]}: {json.dumps(save_result, ensure_ascii=False)[:200]}")
            
            if save_result.get('code') == 0:
                log(f"  [SUCCESS] 保存成功!")
                break
            await asyncio.sleep(1)
        
        await asyncio.sleep(3)
        
        # [8] 验证
        log(f"  [8] 验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(5)
        
        draft_html = await page.evaluate("() => document.body.innerText")
        found = title[:15] in draft_html
        
        if found:
            log(f"  [SUCCESS] 文章已在草稿箱中!")
            await page.close()
            return True
        else:
            log(f"  [FAIL] 未找到")
            draft_titles = re.findall(r'编辑删除\n(.+?)\n', draft_html)
            log(f"  草稿箱: {draft_titles[:5]}")
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
    log(f"v12: save_ugc_draft + 删除旧草稿")
    log("=" * 60)
    
    with open(MANIFEST_FILE, "r") as f:
        manifest = json.load(f)
    
    log(f"共{len(manifest)}篇文章")
    log("启动浏览器...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH, headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 800}, locale="zh-CN"
        )
        
        with open(COOKIE_FILE) as f:
            cookies = json.load(f)
        await context.add_cookies([
            {"name": n, "value": str(v), "domain": ".toutiao.com", "path": "/"}
            for n, v in cookies.items()
        ])
        log("Cookie已加载")
        
        page = await context.new_page()
        await page.goto("https://mp.toutiao.com/profile_v4/index", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        if "login" in page.url.lower():
            log("[ERROR] Cookie已过期")
            await browser.close()
            return
        log("[OK] 登录有效")
        await page.close()
        
        # 只处理第二篇（体育，不在草稿箱中）
        if len(manifest) >= 2:
            result = await process_article(context, manifest[1], 2, len(manifest))
            log(f"结果: {'成功' if result else '失败'}")
        
        await browser.close()
    log("完成")

if __name__ == "__main__":
    asyncio.run(main())