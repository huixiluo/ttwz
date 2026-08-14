#!/usr/bin/env python3
"""v5: 捕获pgc_id + 使用正确参数直接调用保存API"""
import os, re, json, time, base64, asyncio, io, urllib.parse
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"
LOG_FILE = os.path.join(BASE_DIR, "upload_v5.log")

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
                    const masks = document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .ant-modal-mask');
                    masks.forEach(m => m.remove());
                    const btns = document.querySelectorAll('button, span, .byte-btn');
                    for (const b of btns) {
                        const t = (b.textContent || '').trim();
                        if (t === '关闭' || t === '取消' || t === '知道了' || t === '不恢复') {
                            b.click(); return;
                        }
                    }
                }
            """)
            await asyncio.sleep(0.5)
        except:
            break

async def wait_for_editor(page, timeout=30):
    for i in range(timeout):
        pm_exists = await page.evaluate("() => !!document.querySelector('.ProseMirror')")
        if pm_exists: return True
        await asyncio.sleep(1)
    return False

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

    # 捕获 article/new 响应（获取 pgc_id）
    new_article_data = {}
    article_edit_data = {}
    save_responses = []

    async def on_response(response):
        url = response.url
        if 'article/new' in url and 'format=json' in url:
            try:
                body = await response.text()
                new_article_data['body'] = body
                new_article_data['url'] = url
            except:
                pass
        if 'article/edit' in url and 'pgc_id=' in url:
            try:
                body = await response.text()
                article_edit_data['body'] = body
                article_edit_data['url'] = url
            except:
                pass
        if 'article/publish' in url:
            try:
                body = await response.text()
                save_responses.append({"url": url, "body": body})
            except:
                pass
    page.on('response', on_response)

    try:
        # [1] 打开发布页面
        log(f"  [1] 打开全新发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_popups(page)
        await asyncio.sleep(1)

        if not await wait_for_editor(page):
            log(f"  [ERROR] 编辑器加载超时")
            await page.close()
            return False

        # 分析 article/new 响应
        if new_article_data.get('body'):
            try:
                nd = json.loads(new_article_data['body'])
                log(f"  article/new响应: code={nd.get('code')}, has_data={bool(nd.get('data'))}")
                if nd.get('data'):
                    # 查找 pgc_id
                    data_keys = list(nd['data'].keys())
                    log(f"  data keys: {data_keys[:10]}")
                    pgc_id = nd['data'].get('pgc_id') or nd['data'].get('group_id') or nd['data'].get('id', '')
                    log(f"  pgc_id from new: {pgc_id}")
            except:
                log(f"  article/new解析失败")

        if article_edit_data.get('body'):
            try:
                ed = json.loads(article_edit_data['body'])
                log(f"  article/edit响应: code={ed.get('code')}")
                if ed.get('article_pgc'):
                    pgc = ed['article_pgc']
                    log(f"  loaded pgc_id: {pgc.get('pgc_id')}, title: {str(pgc.get('title',''))[:30]}")
            except:
                pass

        # 检查编辑器状态
        edit_called = await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no_editor';
                const text = editor.textContent || '';
                return text.length > 10 ? 'has_content:' + text.length : 'empty';
            }
        """)
        log(f"  编辑器初始状态: {edit_called}")
        
        if 'has_content' in str(edit_called):
            log(f"  清空旧内容...")
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.innerHTML = '<p><br></p>';
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }
            """)
            await asyncio.sleep(2)
            await dismiss_popups(page)

        await dismiss_popups(page)
        await asyncio.sleep(1)

        # [2] 填标题
        log(f"  [2] 填标题: {title}")
        await page.evaluate("""
            (title) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(el, title);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
            }
        """, title)
        await asyncio.sleep(2)

        # [3] 上传图片
        log(f"  [3] 上传{len(images_base64)}张图片...")
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
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }
            """)
            await asyncio.sleep(0.3)
            await page.evaluate("() => { const editor = document.querySelector('.ProseMirror'); if (editor) editor.focus(); }")
            await asyncio.sleep(0.2)

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
                    const pasteEvent = new ClipboardEvent('paste', {bubbles: true, cancelable: true});
                    const fakeData = {
                        files: [file], items: [], types: ['Files'],
                        getData: function() { return ''; },
                        setData: function() {}, clearData: function() {}
                    };
                    Object.defineProperty(pasteEvent, 'clipboardData', {
                        value: fakeData, writable: false, configurable: true
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
                log(f"    图片{img_idx+1}: ✓ {img_url[:70]}...")
            else:
                image_urls.append("")

        valid_urls = [u for u in image_urls if u]
        log(f"  [3] 完成: {len(valid_urls)}/{len(images_base64)}张图片已上传")

        # [4] 设置ProseMirror内容
        log(f"  [4] 设置ProseMirror内容...")
        data_json = json.dumps({
            "tp": paragraphs,
            "iu": image_urls,
            "il": image_layout
        }, ensure_ascii=False)

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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length});
}catch(e){
  return JSON.stringify({status:'error',error:e.message});
}
})()""")

        log(f"  PM API结果: {pm_result[:200]}")
        pm_data = json.loads(pm_result) if pm_result else {}

        if pm_data.get('status') == 'ok':
            log(f"  [OK] PM API: {pm_data.get('imgs',0)}张图片, {pm_data.get('chars',0)}字")
        else:
            log(f"  [WARN] PM API失败，使用fallback")
            final_html = ""
            url_idx = 0
            for pi, para in enumerate(paragraphs):
                final_html += f"<p>{para}</p>"
                target = pi + 1
                if target in image_layout:
                    for _ in range(image_layout[target]):
                        if url_idx < len(image_urls) and image_urls[url_idx]:
                            final_html += f'<p><img src="{image_urls[url_idx]}" alt="图片来源于网络"></p>'
                            url_idx += 1
            await page.evaluate("""
                (html) => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.innerHTML = html;
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }
            """, final_html)

        await asyncio.sleep(3)

        # [5] 使用页面API直接保存（带完整参数）
        log(f"  [5] 使用完整参数API保存...")

        # 构建保存内容HTML
        save_html = ""
        url_idx = 0
        for pi, para in enumerate(paragraphs):
            save_html += f"<p>{para}</p>"
            target = pi + 1
            if target in image_layout:
                for _ in range(image_layout[target]):
                    if url_idx < len(image_urls) and image_urls[url_idx]:
                        save_html += f'<div class="pgc-img"><img src="{image_urls[url_idx]}" alt="图片来源于网络"></div>'
                        url_idx += 1

        word_count = len(''.join(paragraphs))

        extra = json.dumps({
            "content_source": 100000000402,
            "content_word_cnt": word_count,
            "is_multi_title": 0,
            "sub_titles": [],
            "gd_ext": {
                "entrance": "",
                "from_page": "publisher_mp",
                "enter_from": "PC",
                "device_platform": "mp",
                "is_message": 0
            },
            "tuwen_wtt_transfer_switch": "1"
        }, ensure_ascii=False)

        # 获取当前页面的 pgc_id
        pgc_id = await page.evaluate("""
            () => {
                // 从 URL 或 Redux store 中获取
                const match = window.location.search.match(/pgc_id=(\d+)/);
                if (match) return match[1];
                // 尝试从 window.__INITIAL_STATE__ 获取
                if (window.__INITIAL_STATE__) {
                    const state = window.__INITIAL_STATE__;
                    return state.article?.pgc_id || state.pgc_id || '';
                }
                return '';
            }
        """)
        log(f"  当前pgc_id: {pgc_id}")

        # 使用 fetch API 保存
        save_result = await page.evaluate("""
            async (args) => {
                const body = new URLSearchParams();
                body.append('article_type', '0');
                body.append('pgc_id', args.pgc_id || '0');
                body.append('source', '29');
                body.append('title', args.title);
                body.append('content', args.content);
                body.append('extra', args.extra);
                body.append('save', '0');
                body.append('entrance', 'main');
                body.append('timer_status', '0');
                body.append('timer_time', '');
                body.append('title_id', '');
                body.append('ic_uri_list', '[]');
                body.append('search_creation_info', '');
                body.append('is_refute_rumor', '0');
                body.append('appid_list', '[]');
                body.append('stock_ids', '[]');
                body.append('concern_list', '[]');
                body.append('comic_attr', '');
                body.append('is_app_preview', '');
                body.append('externalLinkChecked', 'false');
                body.append('externalLink', '');
                body.append('claimOrigin', '0');
                body.append('copyRightChecked', '1');
                body.append('subTitle', '');
                body.append('subCoverList', '[]');
                body.append('coverList', '[]');
                body.append('coverType', '0');
                body.append('articleAdType', '0');
                body.append('isFansArticle', '0');
                body.append('activityId', '');
                body.append('collectionId', '');
                body.append('forum_id', '');
                body.append('is_free', '');
                body.append('is_essence', '');
                body.append('is_live', '');
                body.append('is_original', '');
                body.append('is_pay', '');
                body.append('is_share', '');
                body.append('is_topic', '');
                body.append('is_vote', '');
                body.append('is_watermark', '');
                body.append('latitude', '');
                body.append('longitude', '');
                body.append('city', '');
                body.append('district', '');
                body.append('address', '');
                body.append('poi_id', '');
                body.append('poi_name', '');
                body.append('poi_type', '');
                body.append('is_location', '');
                body.append('is_comment', '');
                body.append('is_original_declare', '');
                body.append('is_original_article', '');
                body.append('original_type', '');
                body.append('is_rumor', '');
                body.append('is_rumor_refute', '');
                body.append('rumor_id', '');
                body.append('is_sync_to_weibo', '');
                body.append('is_sync_to_wechat', '');
                body.append('is_sync_to_qq', '');
                body.append('is_sync_to_qzone', '');
                body.append('is_sync_to_douyin', '');
                body.append('is_sync_to_xigua', '');
                body.append('is_sync_to_huoshan', '');
                body.append('is_sync_to_lark', '');
                body.append('is_sync_to_feishu', '');
                body.append('is_sync_to_dingtalk', '');
                body.append('is_sync_to_wecom', '');
                
                try {
                    const resp = await fetch('/mp/agw/article/publish?source=mp&type=article&aid=1231', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-CSRFToken': document.cookie.match(/passport_csrf_token=([^;]+)/)?.[1] || ''
                        },
                        body: body.toString()
                    });
                    const data = await resp.json();
                    return JSON.stringify(data);
                } catch(e) {
                    return JSON.stringify({error: e.message});
                }
            }
        """, {
            "pgc_id": pgc_id,
            "title": title,
            "content": save_html,
            "extra": extra
        })
        log(f"  API保存结果: {save_result[:500]}")
        
        try:
            sr = json.loads(save_result)
            if sr.get('code') == 0:
                log(f"  [SUCCESS] API保存成功!")
                success = True
            else:
                log(f"  API保存失败: code={sr.get('code')}, msg={sr.get('message', sr.get('reason', ''))}")
                success = False
        except:
            success = False

        # 也触发页面自动保存
        log(f"  触发自动保存...")
        await page.evaluate("""
            (title) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(el, title + 'x');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                setTimeout(() => {
                    nativeSetter.call(el, title);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.blur();
                }, 500);
            }
        """, title)
        await asyncio.sleep(5)

        # 预览触发保存
        await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, span, a, div[role="button"]');
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if (t === '预览' || t.indexOf('预览') !== -1) {
                        b.click(); return;
                    }
                }
            }
        """)
        await asyncio.sleep(5)

        pages = context.pages
        if len(pages) > 1:
            for p in pages:
                if p != page:
                    await p.close()
                    await asyncio.sleep(1)

        # 分析保存结果
        log(f"  [6] 保存结果分析...")
        for resp in save_responses:
            try:
                resp_data = json.loads(resp['body']) if resp['body'] else {}
                code = resp_data.get('code', resp_data.get('err_no', ''))
                msg = resp_data.get('message', resp_data.get('reason', ''))
                log(f"    响应: code={code} msg={msg}")
                if code == 0: success = True
            except:
                pass

        # [7] 验证草稿箱
        log(f"  [7] 验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText")
        title_short = title[:8]
        if title_short in draft_text:
            idx = draft_text.find(title_short)
            log(f"  [SUCCESS] 文章已在草稿箱中!")
            log(f"    {draft_text[idx:idx+120]}")
            success = True
        else:
            log(f"  [FAIL] 未在草稿箱中找到文章")
            log(f"    草稿箱前500字: {draft_text[:500]}")
            success = False

        await page.close()
        return success

    except Exception as e:
        import traceback
        log(f"  [ERROR] 处理异常: {e}")
        log(f"  {traceback.format_exc()}")
        await page.close()
        return False


async def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== 开始运行 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    log("头条草稿箱上传 v5 - API直接保存")

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    log(f"共{len(articles)}篇文章待上传")

    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies_data = json.load(f)

    log("启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-features=IsolateOrigins,site-per-process"]
        )

        context = await browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 900}, locale="zh-CN"
        )

        cookies_list = []
        for name, value in cookies_data.items():
            cookies_list.append({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        await context.add_cookies(cookies_list)

        log("验证登录状态...")
        page = await context.new_page()
        await page.goto("https://mp.toutiao.com", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        current_url = page.url
        if "login" in current_url.lower() or "passport" in current_url.lower():
            log("  [ERROR] 登录已过期")
            await browser.close()
            return
        log("  [OK] 登录有效")
        await page.close()

        success_count = 0
        for i, art in enumerate(articles):
            result = await process_article(context, art, i + 1, len(articles))
            if result:
                success_count += 1

        log(f"\n完成: {success_count}/{len(articles)}篇上传成功")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())