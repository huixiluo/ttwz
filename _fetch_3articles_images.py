# -*- coding: utf-8 -*-
"""为3篇文章获取配图（4层管线：头条→话题页→微博→百度）"""
import json, os, time, base64, hashlib, sys
import requests
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO
import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "body_imgs")
COVERS_DIR = os.path.join(OUTPUT_DIR, "covers")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

ARTICLES_PATH = os.path.join(BASE_DIR, "_articles_3_tt.json")
PREVIEW_PATH = os.path.join(BASE_DIR, "_preview_tt_result.json")

with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
    articles = json.load(f)
with open(PREVIEW_PATH, "r", encoding="utf-8") as f:
    preview = json.load(f)

# 构建关键词→topic_image_url映射
topic_map = {}
for cat in ["娱乐", "体育", "社会"]:
    for h in preview.get(cat, []):
        topic_map[h["word"]] = h.get("image", "")

def process_image(base64_data, max_width=1200, jpeg_quality=92):
    """Pillow处理：保持原比例，加强对比度/锐度/色彩，USM锐化"""
    try:
        img = Image.open(BytesIO(base64_data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if w < 500 or h < 300:
            return None, 0, 0, 0

        # 保持比例缩放到max_width
        if w > max_width:
            ratio = max_width / w
            new_h = int(h * ratio)
            img = img.resize((max_width, new_h), Image.LANCZOS)
            w, h = max_width, new_h

        # 增强
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.12)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.30)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.08)
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=90))

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        data = buf.getvalue()
        return data, w, h, len(data)
    except Exception as e:
        print(f"    [处理失败] {e}")
        return None, 0, 0, 0

def download_image(url):
    """下载图片返回bytes"""
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200 and len(resp.content) >= 8192:
            return resp.content
    except:
        pass
    return None

print("获取头条HTTP session...")
tt_session = ttw.get_tt_session()
print("  OK\n")

all_image_data = {}

for art in articles:
    idx = art["index"]
    keyword = art["keyword"]
    topic_image = topic_map.get(keyword, "")
    topic_url = ""  # from preview
    # 从preview找URL
    for cat in ["娱乐", "体育", "社会"]:
        for h in preview.get(cat, []):
            if h["word"] == keyword:
                topic_url = h.get("url", "")
                break

    print(f"[{idx}/3] [{art['category']}] {keyword}")
    print(f"  4层管线获取5张配图...")

    images, source = ttw.fetch_images_unified(
        tt_session, keyword, topic_image_url=topic_image, topic_url=topic_url, count=5
    )
    print(f"  来源: {source}")

    # 处理图片
    processed = []
    for i, img_data in enumerate(images):
        if isinstance(img_data, str):
            # base64 string
            if img_data.startswith("http"):
                raw = download_image(img_data)
                if raw:
                    img_data = raw
                else:
                    print(f"    图{i+1}: 下载失败, 跳过")
                    continue
            else:
                try:
                    img_data = base64.b64decode(img_data)
                except:
                    # 可能已经是bytes
                    if isinstance(img_data, str):
                        print(f"    图{i+1}: 格式不支持, 跳过")
                        continue
                    img_data = img_data.encode() if isinstance(img_data, str) else img_data

        data, w, h, size = process_image(img_data)
        if data:
            processed.append((data, w, h, size))
            print(f"    图{i+1}: {w}x{h}, {size//1024}KB")
        else:
            print(f"    图{i+1}: 分辨率不足或处理失败, 跳过")

    if len(processed) < 5:
        print(f"  ⚠ 只有{len(processed)}张有效图片, 需补充!")
        remaining = 5 - len(processed)
        # 短关键词变体用于百度搜索
        kw_variants = [keyword]
        if " " in keyword:
            kw_variants.append(keyword.split(" ")[0])  # 只取前半
        # 针对特定话题的短关键词
        if "男篮" in keyword:
            kw_variants.extend(["中国男篮", "篮球比赛"])
        elif "高温" in keyword:
            kw_variants.extend(["深圳高温", "高温天气", "酷暑"])
        elif "结婚" in keyword or "领证" in keyword:
            kw_variants.extend(["结婚登记", "领证"])
        for kw_v in kw_variants:
            if len(processed) >= 5:
                break
            print(f"    百度搜索: {kw_v}")
            bd_imgs = ttw.fetch_images_baidu(kw_v, count=remaining + 5)
            for img_data in bd_imgs:
                if len(processed) >= 5:
                    break
                # fetch_images_baidu 返回的是base64字符串
                if isinstance(img_data, str):
                    try:
                        decoded = base64.b64decode(img_data)
                        # 使用Pillow处理（保持比例，max1200px）
                        data, w, h, size = process_image(decoded)
                        if data:
                            processed.append((data, w, h, size))
                            print(f"    补图: {w}x{h}, {size//1024}KB")
                    except:
                        continue
                else:
                    data, w, h, size = process_image(img_data)
                    if data:
                        processed.append((data, w, h, size))
                        print(f"    补图: {w}x{h}, {size//1024}KB")

    # 保存
    img_paths = []
    for i, (data, w, h, size) in enumerate(processed[:5]):
        fname = f"body_img_{idx}_{i+1}.jpg"
        fpath = os.path.join(IMAGES_DIR, fname)
        with open(fpath, "wb") as f:
            f.write(data)
        img_paths.append(fpath)

    all_image_data[keyword] = {
        "index": idx,
        "category": art["category"],
        "source": source,
        "image_paths": img_paths,
        "image_count": len(img_paths),
    }
    print(f"  保存 {len(img_paths)} 张到 {IMAGES_DIR}/")

# 保存图片数据
img_data_path = os.path.join(BASE_DIR, "_image_data_3_tt.json")
with open(img_data_path, "w", encoding="utf-8") as f:
    json.dump(all_image_data, f, ensure_ascii=False, indent=2)

print(f"\n图片数据已保存: {img_data_path}")
print(f"总计: {sum(v['image_count'] for v in all_image_data.values())} 张图片")