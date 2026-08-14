#!/usr/bin/env python3
"""Linux版头条草稿箱上传 - 基于 upload_visible.py 的ProseMirror API方案"""
import os, re, json, time, base64, asyncio
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ============ 图片布局计算 ============
def calc_image_layout(total_paragraphs, num_images=5):
    if total_paragraphs < 1:
        return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}

    def _build_positions(last):
        if last < 3:
            return [1]
        pos_list = [1]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - 1) / n_groups
            for k in range(1, n_groups + 1):
                raw = 1 + step * k if k < n_groups else last
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


# ============ 提取HTML内容 ============
def extract_html_content(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if body_match:
        body = body_match.group(1)
    else:
        body = html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
        images.append(m.group(1))
    return paragraphs, images


# ============ ProseMirror JS ============
PM_SET_CONTENT_JS = r"""(function(){
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
})()"""


async def upload_images_get_urls(page, html_path):
    """从HTML中提取图片，逐张上传到编辑器获取服务器URL"""
    paragraphs, images = extract_html_content(html_path)
    if not images:
        return [], paragraphs

    image_urls = []
    for img_idx, data_url in enumerate(images):
        print(f"    图片{img_idx+1}: 上传中...")

        # 解析base64
        try:
            header, b64 = data_url.split(',', 1)
            mime = header.split(':')[1].split(';')[0]
            ext = mime.split('/')[-1].replace('jpeg', 'jpg')
            img_bytes = base64.b64decode(b64)
        except Exception as e:
            print(f"      解析失败: {e}")
            image_urls.append("")
            continue

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
        await asyncio.sleep(0.3)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.2)

        # 粘贴Blob上传图片
        b64_str = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                const b = "{b64_str}";
                const bs = atob(b);
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img_{img_idx}.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                const fd = {{
                    files: [file], items: [], types: ['Files'],
                    getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}
                }};
                Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                editor.dispatchEvent(ev);
            }}
        """)

        # 等待图片出现
        img_url = ""
        for _ in range(60):
            await asyncio.sleep(1)
            img_url = await page.evaluate("""
                () => {
                    const img = document.querySelector('.ProseMirror img');
                    return img ? img.src : '';
                }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break

        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            print(f"      OK: {img_url[:70]}...")
            image_urls.append(img_url)
        else:
            print(f"      FAIL: {img_url[:50] if img_url else '无图片'}")
            image_urls.append("")

        await asyncio.sleep(0.5)

    return image_urls, paragraphs


async def set_content_via_pm(page, paragraphs, image_urls, image_layout):
    """通过ProseMirror view.dispatch()设置完整内容"""
    valid_urls = [u for u in image_urls if u and not u.startswith('blob:')]

    data = {
        "tp": paragraphs,
        "iu": image_urls,  # 使用原始URL列表（含空字符串），保持索引一致
        "il": image_layout
    }
    data_json = json.dumps(data, ensure_ascii=False)

    await page.evaluate(f"window._pmData = {data_json};")

    result = await page.evaluate(PM_SET_CONTENT_JS)
    return result


async def process_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]
    cover_files = art.get("cover_files", [])

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] HTML文件不存在: {html_path}")
        return False

    # 导航到发布页面
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btns = page.locator(f"text={btn_text}")
            count = await btns.count()
            if count > 0:
                await btns.first.click()
                await asyncio.sleep(1)
    except:
        pass

    # 等待编辑器就绪
    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  [ERROR] 编辑器未就绪")
        return False

    print("  [OK] 编辑器就绪")

    # 步骤1: 上传图片获取服务器URL
    print("  [1] 上传图片...")
    image_urls, paragraphs = await upload_images_get_urls(page, html_path)
    valid_urls = [u for u in image_urls if u]
    print(f"  图片上传: {len(valid_urls)}/{len(image_urls)}张成功")

    # 步骤2: 计算图片布局
    image_layout = calc_image_layout(len(paragraphs), len(image_urls))
    print(f"  图片布局: {image_layout}")

    # 步骤3: 通过ProseMirror API设置内容
    print("  [2] 设置编辑器内容...")
    pm_result = await set_content_via_pm(page, paragraphs, image_urls, image_layout)
    print(f"  PM API结果: {pm_result}")

    pm_data = None
    try:
        pm_data = json.loads(pm_result) if pm_result else None
    except:
        pass

    pm_success = pm_data and pm_data.get('status') == 'ok'

    if pm_success:
        imgs = pm_data.get('imgs', 0)
        chars = pm_data.get('chars', 0)
        print(f"  [OK] PM设置成功: {chars}字, {imgs}张图片")
    else:
        print(f"  [WARN] PM API失败，尝试回退方案...")
        # 回退：逐段键盘输入
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

        editor_el = page.locator('.ProseMirror').first
        await editor_el.click()
        await asyncio.sleep(0.3)

        img_idx = 0
        for pi, para_text in enumerate(paragraphs):
            await editor_el.click()
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=3)
            await asyncio.sleep(0.2)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.2)

            target_para = pi + 1
            if target_para in image_layout:
                for _ in range(image_layout[target_para]):
                    if img_idx < len(valid_urls):
                        img_url = valid_urls[img_idx]
                        await page.evaluate(f"""
                            () => {{
                                const editor = document.querySelector('.ProseMirror');
                                if (!editor) return;
                                editor.focus();
                                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                                const cd = {{
                                    types: ['text/html'],
                                    getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" />' : ''; }},
                                    setData: function() {{}},
                                    clearData: function() {{}},
                                    files: [], items: []
                                }};
                                Object.defineProperty(ev, 'clipboardData', {{value: cd}});
                                editor.dispatchEvent(ev);
                            }}
                        """)
                        await asyncio.sleep(0.5)
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(0.3)
                        img_idx += 1

    # 步骤4: 等待图片URL变为服务器URL
    if valid_urls:
        print("  [3] 等待图片同步...")
        for _ in range(20):
            await asyncio.sleep(2)
            srcs = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('.ProseMirror img');
                    return Array.from(imgs).map(i => i.src);
                }
            """) or []
            blob_count = sum(1 for s in srcs if s.startswith('blob:') or s.startswith('data:'))
            server_count = len(srcs) - blob_count
            if blob_count == 0 and server_count > 0:
                print(f"  [OK] 所有图片已同步 ({server_count}张)")
                break
        else:
            print(f"  [WARN] 图片同步可能未完成")

    # 步骤5: 填写标题
    print("  [4] 填写标题...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click()
    await asyncio.sleep(0.5)

    # 使用React兼容方式设置标题
    title_json = json.dumps(title)
    await page.evaluate(f"""
        () => {{
            const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                      document.querySelector('textarea[placeholder*="请输入文章标题"]');
            if (!el) return 'not_found';
            el.focus();
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeSetter.call(el, {title_json});
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
            return el.value;
        }}
    """)
    await asyncio.sleep(3)
    print(f"  标题: {title}")

    # 步骤6: 触发保存
    print("  [5] 触发保存...")
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.dispatchEvent(new Event('input', {bubbles: true}));
                editor.dispatchEvent(new Event('change', {bubbles: true}));
            }
            const titleEl = document.querySelector('textarea[placeholder*="文章标题"]');
            if (titleEl) {
                titleEl.dispatchEvent(new Event('blur', {bubbles: true}));
                titleEl.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(5)

    # 截图确认
    await page.screenshot(path=f"/workspace/editor_art{index}.png")
    print(f"  截图: /workspace/editor_art{index}.png")

    # 步骤7: 验证草稿箱
    print("  [6] 验证草稿箱...")
    await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(5)

    draft_text = await page.evaluate("() => document.body.innerText")
    title_short = title[:6]
    if title_short in draft_text:
        idx = draft_text.find(title_short)
        print(f"  [SUCCESS] 文章在草稿箱中!")
        print(f"    {draft_text[idx:idx+80]}")
        return True
    else:
        print(f"  [FAIL] 未在草稿箱中找到文章")
        print(f"  草稿箱前500字: {draft_text[:500]}")
        return False


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    print(f"Chrome: {CHROME_PATH}")

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
        cookie_list = [
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 验证登录
        print("验证登录...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        page_title = await page.title()
        if "登录" in page_title:
            print("[ERROR] Cookie已过期，需要重新登录")
            await browser.close()
            return
        print("[OK] 登录有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await process_article(page, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(3)

        # 最终验证
        print(f"\n{'='*60}")
        print(f"最终验证草稿箱...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        for art in articles:
            t = art["title"][:6]
            found = t in draft_content
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_box_final.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())