#!/usr/bin/env python3
"""v15: 全新发布页面 + 键盘输入 + 正确保存

关键发现：
- 发布页面会加载旧文章（pgc_id=7673791290261979694）
- 保存API需要正确的pgc_id
- 需要先获取新pgc_id或使用正确的保存端点
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
return JSON.stringify({status: 'ok', inserted: inserted, totalImgs: finalImgs});
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


async def upload_cover(page, cover_paths):
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("    无有效封面图，跳过")
        return
    print(f"    上传{len(valid)}张封面...")
    await page.evaluate("window.scrollTo(0, 0);")
    await asyncio.sleep(1)
    await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if (r.value === '3') { r.click(); r.dispatchEvent(new Event('change', {bubbles: true})); return; }
            }
        }
    """)
    await asyncio.sleep(2)
    for ci, cf in enumerate(valid):
        print(f"      封面{ci+1}: {os.path.basename(cf)}...", end=" ", flush=True)
        await page.evaluate("""
            () => { const add = document.querySelector('.article-cover-add'); if (add) { add.scrollIntoView({block: 'center'}); add.click(); } }
        """)
        await asyncio.sleep(1.5)
        uploaded = False
        try:
            file_input = page.locator('input[type="file"][accept*="image"]').first
            await file_input.set_input_files(cf, timeout=5000)
            await asyncio.sleep(2)
            uploaded = True
        except:
            try:
                all_inputs = page.locator('input[type="file"]')
                count = await all_inputs.count()
                for i in range(count):
                    inp = all_inputs.nth(i)
                    if await inp.is_visible():
                        await inp.set_input_files(cf, timeout=3000)
                        await asyncio.sleep(2)
                        uploaded = True
                        break
            except: pass
        print("OK" if uploaded else "FAIL")


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
    print(f"  内容: {len(paragraphs)}段, {len(images)}张图")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")

    page = await context.new_page()

    # 拦截所有API请求
    all_requests = []
    all_responses = []

    async def on_request(request):
        url = request.url
        if "mp.toutiao.com" in url and "/mp/agw/" in url:
            try:
                post_data = request.post_data
                all_requests.append({
                    "url": url[:250],
                    "method": request.method,
                    "body": (post_data or "")[:1500]
                })
            except: pass

    async def on_response(response):
        url = response.url
        if "mp.toutiao.com" in url and "/mp/agw/" in url:
            try:
                body = await response.text()
                body = body[:600]
            except: body = "[err]"
            all_responses.append({
                "url": url[:250],
                "status": response.status,
                "body": body
            })

    page.on("request", on_request)
    page.on("response", on_response)

    try:
        # 删除旧文章（pgc_id=7673791290261979694），然后打开全新页面
        print(f"  [0] 清理旧草稿...")
        # 先打开草稿页，删除旧文章
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # 删除旧文章
        delete_count = await page.evaluate("""
            () => {
                const delBtns = document.querySelectorAll('button, span, a');
                let count = 0;
                for (const b of delBtns) {
                    if ((b.textContent || '').trim() === '删除') {
                        b.click();
                        count++;
                    }
                }
                return count;
            }
        """)
        print(f"  找到{delete_count}个删除按钮")

        # 确认删除弹窗
        await asyncio.sleep(2)
        try:
            confirm_btn = page.locator("text=确定").first
            if await confirm_btn.is_visible(timeout=3000):
                await confirm_btn.click()
                print(f"  已确认删除")
                await asyncio.sleep(3)
        except: pass

        # 现在打开全新发布页面
        print(f"  [1] 打开全新发布页面...")
        await page.goto(PUBLISH_URL + "?_t=" + str(int(time.time() * 1000)), wait_until="domcontentloaded", timeout=30000)
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

        # 检查是否加载了旧文章
        edit_api = [r for r in all_requests if 'article/edit' in r.get('url', '')]
        new_api = [r for r in all_requests if 'article/new' in r.get('url', '')]
        if edit_api:
            print(f"  [WARN] 页面加载了旧文章!")
        if new_api:
            print(f"  [OK] 页面调用了new API")

        # 打印new API响应
        new_resps = [r for r in all_responses if 'article/new' in r.get('url', '')]
        for nr in new_resps:
            print(f"  new API: {nr['body'][:300]}")

        # [2] 上传图片
        image_urls = []
        if img_bytes_list:
            print(f"  [2] 上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid_count = len([u for u in image_urls if u])
            print(f"  上传完成: {valid_count}/{len(img_bytes_list)}张成功")
        valid_urls = [u for u in image_urls if u]

        # [3] 清空编辑器
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

        # 打印publish API请求和响应
        print(f"\n  API分析:")
        publish_resps = [r for r in all_responses if 'publish' in r.get('url', '') and 'article' in r.get('url', '')]
        for pr in publish_resps:
            print(f"    publish响应: {pr['body'][:300]}")

        # 等待保存
        print(f"  等待保存...")
        saved = False
        for i in range(20):
            await asyncio.sleep(1)
            s = await page.evaluate("""
                () => { const body = document.body.innerText; return body.indexOf('草稿已保存') !== -1; }
            """)
            if s:
                print(f"  [OK] 保存成功！(第{i+1}秒)")
                saved = True
                break

        # 上传封面
        await upload_cover(page, cover_files)
        await asyncio.sleep(3)

        await page.screenshot(path=f"/workspace/v15_art{index}.png")
        return saved

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v15_art{index}_err.png")
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

        print(f"\n  草稿箱内容:")
        draft_lines = [l.strip() for l in draft_text.split('\n') if l.strip() and len(l.strip()) > 5]
        for line in draft_lines[:20]:
            print(f"    {line[:100]}")

        await verify_page.screenshot(path="/workspace/draft_v15_final.png")
        await verify_page.close()
        await browser.close()

    print(f"\n上传完成: {success}/{len(articles)} 篇成功")


if __name__ == "__main__":
    asyncio.run(main())