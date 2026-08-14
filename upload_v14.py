#!/usr/bin/env python3
"""头条草稿箱上传 v14 - 找保存按钮 + 网络请求拦截

策略：
1. 键盘输入文字 + PM API插入图片
2. 找页面上的"保存草稿"/"存草稿"按钮点击
3. 拦截请求体查看保存参数
4. 如果保存按钮不可用，拦截save_ugc_draft请求分析参数
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
        () => { document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper, [class*="drawer-mask"], [class*="modal-mask"]').forEach(m => { if (m && m.parentNode) m.parentNode.removeChild(m); }); }
    """)
    await asyncio.sleep(0.3)


async def dismiss_notifications(page):
    await remove_overlays(page)
    for btn_text in ["关闭", "不恢复", "知道了", "确定", "取消"]:
        try:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await asyncio.sleep(0.3)
        except: pass


async def upload_images_get_urls(page, img_bytes_list):
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_overlays(page)
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = '<p></p>'; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)
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
        img_url = ""
        for _ in range(60):
            await asyncio.sleep(0.5)
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'): break
        ok = img_url and not img_url.startswith('blob:') and not img_url.startswith('data:')
        print("OK" if ok else "FAIL")
        image_urls.append(img_url if ok else "")
        await asyncio.sleep(0.3)
    return image_urls


async def clear_editor_via_pm(page):
    """通过PM API清空编辑器"""
    result = await page.evaluate("""(function(){
function findView(){
  var editor = document.querySelector('.ProseMirror');
  if (!editor) return null;
  var desc = editor.pmViewDesc;
  while (desc) { if (desc.view && desc.view.state) return desc.view; desc = desc.parent; }
  function sf(fiber, v) {
    if (!fiber || v.has(fiber) || v.size > 500) return null;
    v.add(fiber);
    if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
    if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
    if (fiber.memoizedState) {
      var s = fiber.memoizedState;
      while (s) { if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view; s = s.next; }
    }
    var r = sf(fiber.child, v); if (r) return r;
    return sf(fiber.sibling, v);
  }
  var el = editor;
  for (var i = 0; i < 15 && el; i++) {
    var fk = Object.keys(el).find(function(k) { return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0; });
    if (fk) { var v = new Set(); var r = sf(el[fk], v); if (r) return r; }
    el = el.parentElement;
  }
  return null;
}
var view = findView();
if (!view) return 'no_view';
var tr = view.state.tr;
tr.replaceWith(0, view.state.doc.content.size, view.state.schema.nodes.doc.createAndFill().content);
view.dispatch(tr);
return 'ok';
})()""")
    return result


async def insert_images_via_pm(page, valid_urls, image_layout, total_paragraphs):
    print(f"    通过PM API插入{len(valid_urls)}张图片...")
    data_json = json.dumps({"iu": valid_urls, "il": image_layout, "tp_count": total_paragraphs}, ensure_ascii=False)
    await page.evaluate("window._pmImgData=" + data_json + ";")

    result = await page.evaluate("""(function(){
var data = window._pmImgData;
function findView(){
  var editor = document.querySelector('.ProseMirror');
  if (!editor) return null;
  var desc = editor.pmViewDesc;
  while (desc) { if (desc.view && desc.view.state) return desc.view; desc = desc.parent; }
  function sf(fiber, v) {
    if (!fiber || v.has(fiber) || v.size > 500) return null;
    v.add(fiber);
    if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
    if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
    if (fiber.memoizedState) {
      var s = fiber.memoizedState;
      while (s) { if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view; s = s.next; }
    }
    var r = sf(fiber.child, v); if (r) return r;
    return sf(fiber.sibling, v);
  }
  var el = editor;
  for (var i = 0; i < 15 && el; i++) {
    var fk = Object.keys(el).find(function(k) { return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0; });
    if (fk) { var v = new Set(); var r = sf(el[fk], v); if (r) return r; }
    el = el.parentElement;
  }
  return null;
}
var view = findView();
if (!view) return JSON.stringify({status: 'no_view'});
var schema = view.state.schema;
var nts = Object.keys(schema.nodes);
var pn = null, im = null;
nts.forEach(function(k) {
  if (k === 'paragraph' || k === 'para') pn = k;
  if (k === 'image' || k === 'imageUpload' || k === 'media' || k === 'img') im = k;
});
if (!im) nts.forEach(function(k) { if (k.toLowerCase().indexOf('image') >= 0 || k.toLowerCase().indexOf('media') >= 0) im = k; });
if (!pn) nts.forEach(function(k) { if (k.toLowerCase().indexOf('para') >= 0) pn = k; });
if (!pn || !im) return JSON.stringify({status: 'no_types', nodes: nts});
var imSpec = schema.nodes[im];
var urlAttr = 'src';
var imAttrs = {};
if (imSpec && imSpec.spec && imSpec.spec.attrs) {
  Object.keys(imSpec.spec.attrs).forEach(function(an) {
    var a = imSpec.spec.attrs[an];
    if (an === 'src' || an === 'url' || an === 'href') urlAttr = an;
    imAttrs[an] = a && a.default !== undefined ? a.default : '[no-default]';
  });
}
var hasDataAttr = imAttrs && Object.keys(imAttrs).indexOf('data') >= 0;
var doc = view.state.doc;
var paraPositions = [];
doc.descendants(function(node, pos) {
  if (node.type.name === pn) paraPositions.push(pos);
  return true;
});
if (paraPositions.length < data.tp_count) {
  return JSON.stringify({status: 'para_mismatch', expected: data.tp_count, actual: paraPositions.length});
}
var tr = view.state.tr;
var imgIdx = 0;
var inserted = 0;
var sortedKeys = Object.keys(data.il).map(Number).sort(function(a, b) { return b - a; });
for (var ki = 0; ki < sortedKeys.length; ki++) {
  var targetPara = sortedKeys[ki];
  var numImgs = data.il[targetPara];
  var paraIdx = targetPara - 1;
  if (paraIdx < paraPositions.length) {
    var paraPos = paraPositions[paraIdx];
    var paraNode = doc.nodeAt(paraPos);
    if (paraNode) {
      var insertPos = paraPos + paraNode.nodeSize;
      for (var j = numImgs - 1; j >= 0; j--) {
        var urlIdx = data.iu.length - 1 - (imgIdx + j);
        if (urlIdx >= 0) {
          var imgUrl = data.iu[urlIdx];
          var attrs = {};
          if (hasDataAttr) {
            attrs.data = {url: imgUrl, icUri: imgUrl, catchErrorUrl: '', link: '', caption: '图片来源于网络', ic: false, naturalHeight: 0, naturalWidth: 0, srcType: '', captionLenErr: false, needCheck: false};
          } else {
            attrs[urlAttr] = imgUrl;
            attrs.alt = '图片来源于网络';
          }
          var imgNode = schema.nodes[im].create(attrs);
          tr = tr.insert(insertPos, imgNode);
          inserted++;
        }
      }
      imgIdx += numImgs;
    }
  }
}
if (inserted > 0) view.dispatch(tr);
var finalImgs = 0;
view.state.doc.descendants(function(node) { if (node.type.name === im) finalImgs++; return true; });
return JSON.stringify({status: 'ok', inserted: inserted, totalImgs: finalImgs, nodes: nts, pn: pn, im: im, urlAttr: urlAttr, hasDataAttr: hasDataAttr, paraCount: paraPositions.length});
})()""")
    return result


async def fill_title(page, title):
    await page.evaluate(f"""
        () => {{
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.focus();
            const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            ns.call(el, {json.dumps(title)});
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
        }}
    """)


async def wait_for_save_indicator(page, timeout=20):
    for i in range(timeout):
        await asyncio.sleep(1)
        saved = await page.evaluate("""
            () => { const body = document.body.innerText; return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1; }
        """)
        if saved: return True
    return False


async def trigger_save(page):
    await page.evaluate("""
        () => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.focus();
            el.dispatchEvent(new KeyboardEvent('keydown', {key: ' ', bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }
    """)
    await asyncio.sleep(0.3)
    await page.evaluate("""
        () => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.blur();
        }
    """)


async def process_article(context, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  内容: {len(paragraphs)}段, {len(images)}张图")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")

    page = await context.new_page()

    # 拦截所有请求和响应
    save_requests = []
    save_responses = []

    async def on_request(request):
        url = request.url
        if "mp.toutiao.com" in url and ("save" in url.lower() or "draft" in url.lower() or "publish" in url.lower()):
            try:
                post_data = request.post_data
                if post_data:
                    save_requests.append({"url": url[:200], "method": request.method, "body": post_data[:2000]})
            except: pass

    async def on_response(response):
        url = response.url
        if "mp.toutiao.com" in url and ("save" in url.lower() or "draft" in url.lower() or "publish" in url.lower()):
            try:
                body = await response.text()
                body = body[:500]
            except: body = "[err]"
            save_responses.append({"url": url[:200], "status": response.status, "body": body})

    page.on("request", on_request)
    page.on("response", on_response)

    try:
        print(f"  [1] 打开发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
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

        # [2] 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"  [2] 上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid_count = len([u for u in image_urls if u])
            print(f"  上传完成: {valid_count}/{len(img_bytes_list)}张成功")
        valid_urls = [u for u in image_urls if u]

        # [3] 通过PM API清空编辑器
        print(f"  [3] 清空编辑器...")
        clear_result = await clear_editor_via_pm(page)
        print(f"  清空: {clear_result}")
        await asyncio.sleep(0.5)

        # [4] 键盘输入文字
        print(f"  [4] 键盘输入{len(paragraphs)}段文字...")
        await remove_overlays(page)
        for pi, para_text in enumerate(paragraphs):
            await remove_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=0)
            await asyncio.sleep(0.1)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.1)
            if (pi + 1) % 3 == 0:
                print(f"    已输入 {pi+1}/{len(paragraphs)} 段...")
        print(f"  文字输入完成")

        # 验证PM状态中的文字
        await asyncio.sleep(1)
        pm_chars = await page.evaluate("""(function(){
function findView(){
  var editor = document.querySelector('.ProseMirror');
  if (!editor) return null;
  var desc = editor.pmViewDesc;
  while (desc) { if (desc.view && desc.view.state) return desc.view; desc = desc.parent; }
  function sf(fiber, v) {
    if (!fiber || v.has(fiber) || v.size > 500) return null;
    v.add(fiber);
    if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
    if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
    if (fiber.memoizedState) {
      var s = fiber.memoizedState;
      while (s) { if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view; s = s.next; }
    }
    var r = sf(fiber.child, v); if (r) return r;
    return sf(fiber.sibling, v);
  }
  var el = editor;
  for (var i = 0; i < 15 && el; i++) {
    var fk = Object.keys(el).find(function(k) { return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0; });
    if (fk) { var v = new Set(); var r = sf(el[fk], v); if (r) return r; }
    el = el.parentElement;
  }
  return null;
}
var view = findView();
if (!view) return 'no_view';
return view.state.doc.textContent.length;
})()""")
        print(f"  PM文字数: {pm_chars}")

        # [5] 插入图片
        if valid_urls:
            print(f"  [5] 插入{len(valid_urls)}张图片...")
            pm_result = await insert_images_via_pm(page, valid_urls, image_layout, len(paragraphs))
            print(f"  PM结果: {pm_result}")
            await asyncio.sleep(2)
            dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
            print(f"  DOM图片数: {dom_imgs}")

        # [6] 填写标题
        print(f"  [6] 填写标题...")
        await fill_title(page, title)
        await asyncio.sleep(3)

        # [7] 查找并点击保存按钮
        print(f"  [7] 查找保存按钮...")
        await remove_overlays(page)

        # 扫描页面上所有按钮
        buttons_info = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, a, span[role="button"], div[role="button"]');
                const result = [];
                for (const b of btns) {
                    const text = (b.textContent || '').trim();
                    if (text && text.length < 30) {
                        result.push({text: text, tag: b.tagName, visible: b.offsetParent !== null});
                    }
                }
                return result;
            }
        """)
        print(f"  页面按钮:")
        for btn in buttons_info[:30]:
            print(f"    [{btn['tag']}] {btn['text'][:50]} (visible={btn['visible']})")

        # 尝试点击保存草稿按钮
        save_clicked = False
        for selector in [
            "text=保存草稿",
            "text=存草稿",
            "text=保存",
            "button:has-text('保存')",
            "button:has-text('草稿')",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    print(f"  已点击: {selector}")
                    save_clicked = True
                    await asyncio.sleep(3)
                    break
            except: pass

        if not save_clicked:
            print(f"  未找到保存按钮，使用预览触发...")
            try:
                preview_btn = page.locator("text=预览").first
                await preview_btn.click(timeout=5000)
                print(f"  已点击预览")
                await asyncio.sleep(5)
                pages = context.pages
                for p in pages:
                    if p != page:
                        await p.close()
                        await asyncio.sleep(1)
            except:
                await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if ((b.textContent || '').indexOf('预览') !== -1) { b.click(); return; }
                        }
                    }
                """)
                await asyncio.sleep(5)

        # 等待保存
        await wait_for_save_indicator(page, timeout=15)

        # 打印请求和响应
        print(f"\n  保存请求 ({len(save_requests)}):")
        for req in save_requests:
            print(f"    {req['method']} {req['url'][:80]}")
            if req.get('body'):
                print(f"      body: {req['body'][:300]}")

        print(f"\n  保存响应 ({len(save_responses)}):")
        for resp in save_responses:
            print(f"    {resp['status']} {resp['url'][:80]}")
            print(f"      body: {resp['body'][:300]}")

        await page.screenshot(path=f"/workspace/v14_art{index}.png")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v14_art{index}_err.png")
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

    # 只处理第一篇文章，用于调试
    article = articles[0]
    print(f"调试文章: {article['title']}")

    html_path = article["html_file"]
    if os.path.exists(html_path):
        paragraphs, images = extract_html_text_and_images(html_path)
        layout = calc_image_layout(len(paragraphs), len(images))
        print(f"  {len(paragraphs)}段 {len(images)}图 布局={layout}\n")

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

        await process_article(context, article, 1, 1)

        await browser.close()

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())