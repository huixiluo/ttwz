# -*- coding: utf-8 -*-
"""用微博补充图片"""
import json, os, base64, time
import requests
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO
from urllib.parse import quote
import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "body_imgs")
os.makedirs(IMAGES_DIR, exist_ok=True)

UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def process_one(img_bytes):
    """处理一张图片"""
    try:
        img = Image.open(BytesIO(img_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if w < 500 or h < 300:
            return None, 0, 0, 0
        if w > 1200:
            ratio = 1200 / w
            h = int(h * ratio)
            w = 1200
            img = img.resize((w, h), Image.LANCZOS)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.12)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.30)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.08)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=90))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=92, optimize=True)
        data = buf.getvalue()
        return data, w, h, len(data)
    except:
        return None, 0, 0, 0

def fetch_weibo_images(keyword, count=5):
    """从微博搜索图片，尝试多个关键词"""
    images = []
    seen = set()
    
    # 尝试不同的搜索关键词
    queries = [f"#{keyword}#"]
    # 短关键词
    if len(keyword) > 4:
        if "男篮" in keyword:
            queries = ["中国男篮", "男篮热身赛", "篮球赛"]
        elif "高温" in keyword:
            queries = ["深圳高温", "高温天气", "高温防暑"]
    
    print("  获取微博访客session...")
    try:
        wb_session = ttw.get_weibo_session()
    except Exception as e:
        print(f"  [微博session失败] {e}")
        return images
    
    for q in queries:
        if len(images) >= count:
            break
        print(f"  搜索: {q}")
        search_url = f"https://weibo.com/ajax/statuses/search?q={quote(q)}"
        try:
            resp = wb_session.get(search_url, headers={
                "User-Agent": UA_PC, "Referer": "https://weibo.com/",
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            statuses = data.get("statuses", [])
            print(f"    找到 {len(statuses)} 条微博")
            for s in statuses:
                if len(images) >= count:
                    break
                pic_infos = s.get("pic_infos", {})
                if not pic_infos:
                    continue
                for pid, info in pic_infos.items():
                    if len(images) >= count:
                        break
                    img_url = (info.get("original", {}).get("url") or
                              info.get("largest", {}).get("url") or
                              info.get("large", {}).get("url") or "")
                    if not img_url or img_url in seen:
                        continue
                    seen.add(img_url)
                    try:
                        ir = wb_session.get(img_url, headers={
                            "User-Agent": UA_PC, "Referer": "https://weibo.com/",
                        }, timeout=20)
                        if ir.status_code == 200 and len(ir.content) > 8000:
                            data, w, h, size = process_one(ir.content)
                            if data:
                                images.append(data)
                                print(f"      ✓ {w}x{h}, {size//1024}KB")
                    except:
                        continue
                    time.sleep(0.2)
        except Exception as e:
            print(f"    搜索失败: {e}")
            continue
        time.sleep(0.5)
    
    return images

# 需要补充的文章
NEED_MORE = {
    2: {"keyword": "中国男篮热身赛险胜乌拉圭", "need": 4},
    3: {"keyword": "深圳高温达极端等级", "need": 2},
}

# 读取已有图片数据
img_data_path = os.path.join(BASE_DIR, "_image_data_3_tt.json")
with open(img_data_path, "r", encoding="utf-8") as f:
    img_data = json.load(f)

for idx, info in NEED_MORE.items():
    kw = info["keyword"]
    need = info["need"]
    print(f"\n[Article {idx}] {kw} - 需要{need}张补充")
    
    existing = img_data.get(kw, {}).get("image_count", 0)
    if existing >= 5:
        print(f"  已有{existing}张, 跳过")
        continue
    
    imgs = fetch_weibo_images(kw, count=need)
    print(f"  获取到{len(imgs)}张")
    
    # 保存
    for i, img_bytes in enumerate(imgs):
        fname = f"body_img_{idx}_{existing + i + 1}.jpg"
        fpath = os.path.join(IMAGES_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(img_bytes)
        print(f"  保存: {fname}")
    
    if kw in img_data:
        img_data[kw]["image_count"] = existing + len(imgs)
        for j in range(len(imgs)):
            fname = f"body_img_{idx}_{existing + j + 1}.jpg"
            img_data[kw]["image_paths"].append(os.path.join(IMAGES_DIR, fname))
        img_data[kw]["source"] = img_data[kw].get("source", "") + f" + 微博补充({len(imgs)}张)"

# 保存更新
with open(img_data_path, "w", encoding="utf-8") as f:
    json.dump(img_data, f, ensure_ascii=False, indent=2)

print(f"\n总计: {sum(v['image_count'] for v in img_data.values())} 张图片")
print("图片数据已更新:", img_data_path)