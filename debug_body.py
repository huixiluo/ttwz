# -*- coding: utf-8 -*-
"""验证body_html内容"""
import os, re, json

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "single_manifest.json")

with open(MANIFEST, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
html_path = art["html_file"]

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
body = body_match.group(1)

parts = []
img_count = 0
for m in re.finditer(
    r'(<p>(.*?)</p>)|'
    r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*<p[^>]*>(.*?)</p>\s*</div>)',
    body, re.DOTALL
):
    if m.group(1):
        parts.append(f'<p>{re.sub(r"<[^>]+>", "", m.group(2))}</p>')
    elif m.group(4):
        caption = m.group(5).strip() if m.group(5) else "图片来源于网络"
        parts.append(f'<p><img src="{m.group(4)[:30]}..." alt="{caption}" /></p>')
        img_count += 1

body_html = "\n".join(parts)

print(f"元素数: {len(parts)}")
print(f"图片数(img标签): {body_html.count('<img ')}")
print(f"图片数(匹配): {img_count}")
print(f"总字符数: {len(body_html)}")
print(f"纯文本字符数: {len(re.sub(r'<[^>]+>', '', body_html))}")
print()

# 检查是否有重复的img
imgs = re.findall(r'<img[^>]*>', body_html)
print(f"所有img标签: {len(imgs)}")
for i, img in enumerate(imgs):
    print(f"  [{i}] {img[:80]}...")