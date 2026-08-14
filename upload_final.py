#!/usr/bin/env python3
"""最终版头条草稿箱上传 - 全新页面 + 逐字键盘输入 + 正确图片布局

策略:
1. 先通过API删除所有旧草稿
2. 打开发布页面（确保是全新文章）
3. 逐字键盘输入标题和正文
4. 按布局规则插入图片
5. 点击保存按钮
"""
import os, re, json, time, base64, asyncio, io, sys
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

LOG_FILE = os.path.join(BASE_DIR, "upload_final.log")

def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"{ts} {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局 - 与 upload_visible.py 一致"""
    if total_paragraphs < 1:
        return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}
    first = 1

    def _build_positions(last):
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
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list

    def _max_gap(pos_list):
        if len(pos_list) < 2:
            return 0
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


def extract_html_content(html_path):
    """从HTML文件中提取纯文字段落和图片base64数据"""
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
    """压缩图片并返回JPEG字节"""
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


async def delete_all_drafts(page):
    """通过API删除所有旧草稿"""
    log("  清理旧草稿...")
    try:
        result = await page.evaluate("""
            async () => {
                try {
                    const resp = await fetch('/mp/agw/creator_center/draft_list?type=2&count=50&app_id=1231');
                    const data = await resp.json();
                    if (data.code !== 0 || !data.draft_list) return 'no_drafts';
                    
                    const drafts = data.draft_list;
                    let deleted = 0;
                    for (const d of drafts) {
                        try {
                            const delResp = await fetch('/mp/agw/creator_center/draft_delete', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                                body: 'draft_id=' + d.gid + '&app_id=1231'
                            });
                            const delData = await delResp.json();
                            if (delData.code === 0) deleted++;
                        } catch(e) {}
                    }
                    return 'deleted:' + deleted + '/' + drafts.length;
                } catch(e) {
                    return 'error:' + e.message;
                }
            }
        """)
        log(f"  清理结果: {result}")
        return result
    except Exception as e:
        log(f"  清理异常: {e}")
        return "error"


async def dismiss_popups(page):
    """关闭各种弹窗"""
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
                            b.click();
                            return;
                        }
                    }
                }
            """)
            await asyncio.sleep(0.5)
        except:
            break


async def wait_for_editor(page, timeout=30):
    """等待编辑器加载就绪"""
    for i in range(timeout):
        pm_exists = await page.evaluate("() => !!document.querySelector('.ProseMirror')")
        if pm_exists:
            return True
        await asyncio.sleep(1)
    return False


async def type_text(page, text):
    """逐字键盘输入文本"""
    # 使用 clipboard paste 方式更快
    await page.evaluate("""
        (text) => {
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return;
            editor.focus();
            // 使用 textarea 作为中介
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
    """, text)
    
    # 粘贴
    await page.keyboard.press('Control+v')
    await asyncio.sleep(0.5)


async def paste_image(page, img_bytes):
    """通过剪贴板粘贴图片"""
    img_b64 = base64.b64encode(img_bytes).decode('ascii')
    paste_result = await page.evaluate("""
        (b64) => {
            const editor = document.querySelector('.ProseMirror');
            if (!editor) return 'no_editor';
            editor.focus();

            const byteString = atob(b64);
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
            const blob = new Blob([ab], {type: 'image/jpeg'});
            const file = new File([blob], 'img.jpg', {type: 'image/jpeg'});

            const pasteEvent = new ClipboardEvent('paste', {
                bubbles: true,
                cancelable: true
            });
            const fakeData = {
                files: [file],
                items: [],
                types: ['Files'],
                getData: function() { return ''; },
                setData: function() {},
                clearData: function() {}
            };
            Object.defineProperty(pasteEvent, 'clipboardData', {
                value: fakeData,
                writable: false,
                configurable: true
            });
            editor.dispatchEvent(pasteEvent);
            return 'ok';
        }
    """, img_b64)
    return paste_result


async def wait_for_image_upload(page, timeout=90):
    """等待图片上传完成，返回服务器URL"""
    for wait_i in range(timeout):
        img_url = await page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('.ProseMirror img');
                if (imgs.length === 0) return 'no_img';
                // 获取最后一张图片
                const lastImg = imgs[imgs.length - 1];
                return lastImg.src || '';
            }
        """)
        if img_url and img_url != 'no_img' and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            return img_url
        await asyncio.sleep(1)
    return ""


async def process_article(context, art, index, total):
    """处理单篇文章 - 全新页面 + 逐字输入"""
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

    if len(paragraphs) < 6:
        log(f"  [WARN] 段落数不足6段，可能影响布局")

    # 计算图片布局
    image_layout = calc_image_layout(len(paragraphs), len(images_base64))
    log(f"  图片布局: {image_layout}")

    # 创建新页面
    page = await context.new_page()

    # 拦截保存响应
    save_responses = []
    async def on_response(response):
        url = response.url
        if 'article/publish' in url:
            try:
                body = await response.text()
                save_responses.append({"url": url, "status": response.status, "body": body[:2000]})
            except:
                pass
    page.on('response', on_response)

    try:
        # [1] 打开发布页面，先清理旧草稿
        log(f"  [1] 打开全新发布页面...")
        
        # 先访问首页清理草稿
        await page.goto("https://mp.toutiao.com", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        await dismiss_popups(page)
        
        # 删除所有旧草稿
        await delete_all_drafts(page)
        await asyncio.sleep(2)
        
        # 现在打开全新发布页面
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_popups(page)
        await asyncio.sleep(1)

        if not await wait_for_editor(page):
            log(f"  [ERROR] 编辑器加载超时")
            await page.close()
            return False

        # 检查是否加载了旧文章
        edit_called = await page.evaluate("""
            () => {
                // 检查页面是否有旧文章内容
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no_editor';
                const text = editor.textContent || '';
                return text.length > 10 ? 'has_content:' + text.length : 'empty';
            }
        """)
        log(f"  编辑器初始状态: {edit_called}")
        
        if 'has_content' in str(edit_called):
            # 清空编辑器
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
        await asyncio.sleep(1)

        # [2] 填标题
        log(f"  [2] 填标题: {title}")
        title_result = await page.evaluate("""
            (title) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return 'not_found';
                el.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(el, title);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
                return el.value;
            }
        """, title)
        log(f"  标题设置结果: {title_result}")
        await asyncio.sleep(2)

        # [3] 上传图片（先上传所有图片，获取URL）
        log(f"  [3] 上传{len(images_base64)}张图片...")
        image_urls = []

        for img_idx, data_url in enumerate(images_base64):
            log(f"    图片{img_idx+1}: 处理中...")
            img_bytes = compress_image(data_url)
            if not img_bytes:
                log(f"    图片{img_idx+1}: 压缩失败，跳过")
                image_urls.append("")
                continue

            # 清空编辑器（只保留一个空段落）
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

            # 聚焦编辑器
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) editor.focus();
                }
            """)
            await asyncio.sleep(0.2)

            # 粘贴图片
            paste_result = await paste_image(page, img_bytes)
            log(f"    粘贴结果: {paste_result}")

            # 等待图片上传
            img_url = await wait_for_image_upload(page)
            if img_url:
                image_urls.append(img_url)
                log(f"    图片{img_idx+1}: ✓ {img_url[:70]}...")
            else:
                log(f"    图片{img_idx+1}: 上传失败")
                image_urls.append("")

        valid_urls = [u for u in image_urls if u]
        log(f"  [3] 完成: {len(valid_urls)}/{len(images_base64)}张图片已上传")

        if not valid_urls:
            log(f"  [ERROR] 没有成功上传的图片")
            await page.close()
            return False

        # [4] 按布局组装内容 - 使用ProseMirror API
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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length,nodes:nts,pn:pn,in:im,urlAttr:urlAttr,imAttrs:imAttrs});
}catch(e){
  return JSON.stringify({status:'error',error:e.message,nodes:nts,pn:pn,in:im,urlAttr:urlAttr});
}
})()""")

        log(f"  PM API结果: {pm_result[:200]}")

        pm_data = None
        try:
            pm_data = json.loads(pm_result) if pm_result else None
        except:
            pass

        if pm_data and pm_data.get('status') == 'ok':
            log(f"  [OK] PM API设置成功: {pm_data.get('imgs',0)}张图片, {pm_data.get('chars',0)}字")
        else:
            log(f"  [WARN] PM API设置失败: {pm_result[:300]}")
            # 回退: 使用 fallback HTML
            log(f"  [FALLBACK] 使用HTML设置内容...")
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

        # [5] 触发保存 - 多种方式
        log(f"  [5] 触发保存...")

        # 方式1: 修改标题触发自动保存
        log(f"    方式1: 修改标题触发自动保存...")
        await page.evaluate("""
            (title) => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                          document.querySelector('textarea[placeholder*="请输入文章标题"]');
                if (!el) return;
                el.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(el, title + ' ');
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
        await asyncio.sleep(4)

        # 方式2: 点击"预览"按钮触发保存
        log(f"    方式2: 点击预览触发保存...")
        preview_clicked = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, span, a, div[role="button"]');
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if (t === '预览' || t.indexOf('预览') !== -1) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            }
        """)
        log(f"    预览按钮: {preview_clicked}")
        await asyncio.sleep(5)

        # 关闭预览页面
        pages = context.pages
        if len(pages) > 1:
            for p in pages:
                if p != page:
                    await p.close()
                    await asyncio.sleep(1)

        # 方式3: Ctrl+S
        log(f"    方式3: Ctrl+S触发保存...")
        await page.evaluate("() => { const editor = document.querySelector('.ProseMirror'); if (editor) editor.focus(); }")
        await asyncio.sleep(0.5)
        await page.keyboard.press('Control+s')
        await asyncio.sleep(4)

        # [6] 分析保存结果
        log(f"  [6] 保存结果分析...")
        success = False
        for resp in save_responses:
            try:
                resp_data = json.loads(resp['body']) if resp['body'] else {}
                code = resp_data.get('code', resp_data.get('err_no', ''))
                msg = resp_data.get('message', resp_data.get('reason', ''))
                log(f"    响应: {resp['status']} code={code} msg={msg}")
                if code == 0:
                    success = True
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
    # 清空日志
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== 开始运行 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    log("头条草稿箱上传 - 最终版")

    # 加载manifest
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    log(f"共{len(articles)}篇文章待上传")

    # 加载cookies
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies_data = json.load(f)

    # 启动浏览器
    log("启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        )

        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )

        # 设置cookies
        cookies_list = []
        for name, value in cookies_data.items():
            cookies_list.append({
                "name": name,
                "value": value,
                "domain": ".toutiao.com",
                "path": "/"
            })
        await context.add_cookies(cookies_list)

        # 先访问首页验证登录
        log("验证登录状态...")
        page = await context.new_page()
        await page.goto("https://mp.toutiao.com", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        current_url = page.url
        log(f"  当前URL: {current_url}")
        if "login" in current_url.lower() or "passport" in current_url.lower():
            log("  [ERROR] 登录已过期，请重新登录")
            await browser.close()
            return
        log("  [OK] 登录有效")
        await page.close()

        # 处理每篇文章
        success_count = 0
        for i, art in enumerate(articles):
            result = await process_article(context, art, i + 1, len(articles))
            if result:
                success_count += 1

        log(f"\n完成: {success_count}/{len(articles)}篇上传成功")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())