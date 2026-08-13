# -*- coding: utf-8 -*-
"""单篇头条热榜文章生成（编辑预撰写模式，无需API，无需config.json）
从 _manual_articles_tt.json 取第1篇（或指定索引），生成HTML+封面
用法：python generate_single_tt.py           # 取第1篇
      python generate_single_tt.py 3         # 取第3篇
"""
import os
import io
import json
import base64
import sys
import datetime
import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def save_cover_images(images_b64, output_dir, prefix):
    cover_dir = os.path.join(output_dir, "covers")
    os.makedirs(cover_dir, exist_ok=True)
    covers = images_b64[:3]
    saved_paths = []
    for i, b64 in enumerate(covers):
        img_bytes = base64.b64decode(b64)
        filename = f"{prefix}_cover_{i+1}.jpg"
        filepath = os.path.join(cover_dir, filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        saved_paths.append(filepath)
    return saved_paths


def main():
    art_index = 0
    if len(sys.argv) > 1:
        try:
            art_index = max(0, int(sys.argv[1]) - 1)
        except ValueError:
            pass

    list_path = os.path.join(BASE_DIR, "_manual_articles_tt.json")
    if not os.path.exists(list_path):
        raise RuntimeError("未找到 _manual_articles_tt.json，需自带category/keyword/title/article")
    with open(list_path, "r", encoding="utf-8") as f:
        arts = json.load(f)

    if art_index >= len(arts):
        raise RuntimeError(f"索引越界：共{len(arts)}篇，请求第{art_index+1}篇")

    a = arts[art_index]
    cat, keyword, title, article = a["category"], a["keyword"], a["title"], a["article"]

    title = ttw.clean_erhua(title)
    article = ttw.clean_erhua(article)

    output_dir = os.path.join(BASE_DIR, "output")
    image_count = 5
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"[{cat}] {keyword}")
    print(f"  标题：{title}（{len(title)}字）")
    print(f"  正文：{len(article)}字")
    if not ttw._is_three_part_title(title):
        print(f"  [警告] 标题非三段式：{title}")
    if len(article) <= 600:
        print(f"  [警告] 正文未超过600字（当前{len(article)}字）")

    print("获取头条HTTP session...")
    session = ttw.get_tt_session()

    print(f"获取配图（目标{image_count}张，优先头条话题页）...")
    images = ttw.fetch_images_from_toutiao(session, keyword, count=image_count)
    source = "头条话题"
    if len(images) < image_count:
        remaining = image_count - len(images)
        fallback = ttw.fetch_images_baidu(keyword, count=remaining)
        images.extend(fallback)
        if fallback:
            source = f"头条话题({len(images)-len(fallback)}) + 百度({len(fallback)})"
    print(f"配图：{len(images)}张（{source}）")

    html = ttw.build_html(title, article, images)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"tt_{cat}_{art_index+1}_{timestamp}"
    filename = f"tt_hot_{prefix}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML已保存：{filepath}")

    cover_paths = save_cover_images(images, output_dir, prefix)
    print(f"封面图：{len(cover_paths)}张 -> {output_dir}/covers/")

    # 保存单篇 manifest（方便 upload_visible 读取）
    single = [{
        "category": cat, "keyword": keyword,
        "title": title, "article": article,
        "html_file": filepath, "cover_files": cover_paths,
        "word_count": len(article),
        "image_count": len(images),
        "image_source": source,
    }]
    manifest_path = os.path.join(BASE_DIR, "single_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(single, f, ensure_ascii=False, indent=2)
    print(f"单篇清单已写入：{manifest_path}，可直接运行 upload_visible.py 上传")


if __name__ == "__main__":
    main()
