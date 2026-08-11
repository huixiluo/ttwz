# -*- coding: utf-8 -*-
"""根据预览结果中的第1条资讯直接生成1篇文章（含三段式标题、真人校准、高清配图、HTML输出）"""
import os
import json
import datetime
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    # 1. 读取预览结果，取第1条资讯
    preview_path = os.path.join(BASE_DIR, "_preview_result.json")
    with open(preview_path, "r", encoding="utf-8") as f:
        preview = json.load(f)

    # 按顺序取第1条：娱乐->体育->社会
    item = None
    item_cat = ""
    for cat in ["娱乐", "体育", "社会"]:
        if preview.get(cat):
            item = preview[cat][0]
            item_cat = cat
            break
    if not item:
        raise RuntimeError("预览结果中没有资讯")

    keyword = item["word"]
    rank = item.get("rank", 1)
    print("=" * 60)
    print(f"选定资讯：[{item_cat}] {item['title']}（热搜排名{rank}，热度{item.get('num', 0)}）")
    print("=" * 60)

    # 2. 配置（编辑直写模式，不依赖config.json，不需要API key）
    output_dir = os.path.join(BASE_DIR, "output")
    image_count = 5
    os.makedirs(output_dir, exist_ok=True)

    # 3. 获取访客session
    print("[1/6] 获取微博访客session...")
    session = hnw.get_visitor_session()
    print("  OK")

    # 4. 读取本地预生成文章内容（DeepSeek余额不足，由编辑直接撰写，已按真人校准标准）
    print("[2/6] 读取本地文章内容（DeepSeek不可用，使用预撰写版本）...")
    content_path = os.path.join(BASE_DIR, "article_content.json")
    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    title = hnw.clean_erhua(content["title"])
    polished = hnw.clean_erhua(content["article"])
    print(f"  标题：{title}（{len(title)}字）")
    print(f"  正文：共 {len(polished)} 字")

    # 5. 标题三段式校验
    print("[3/6] 标题三段式校验...")
    if hnw._is_three_part_title(title):
        print("  通过：标题符合三段式结构（两个逗号分三段）")
    else:
        print(f"  警告：标题非三段式，请检查：{title}")

    # 6. 获取配图（优先微博原帖，不足用百度补）
    print(f"[4/6] 获取配图（优先微博原帖，目标{image_count}张）...")
    images = hnw.fetch_images_from_weibo(session, keyword, count=image_count)
    source = "微博原帖"
    if len(images) < image_count:
        remaining = image_count - len(images)
        fallback = hnw.fetch_images_baidu(keyword, count=remaining)
        images.extend(fallback)
        if fallback:
            source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
    print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

    # 7. 生成HTML
    print("[5/6] 生成HTML...")
    html = hnw.build_html(title, polished, images)

    # 8. 保存文件
    print("[6/6] 保存文件...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"hot_single_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存：{filepath}")

    # 输出摘要
    print()
    print("=" * 60)
    print("文章生成完成")
    print("=" * 60)
    print(f"标题：{title}")
    print(f"字数：{len(polished)}")
    print(f"配图：{len(images)}张（{source}）")
    print(f"文件：{filepath}")
    print()
    print("正文预览：")
    print("-" * 40)
    print(polished[:300] + ("..." if len(polished) > 300 else ""))
    return filepath


if __name__ == "__main__":
    main()
