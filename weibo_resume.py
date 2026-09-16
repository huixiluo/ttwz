#!/usr/bin/env python3
"""断点续传：登录完成后，从weibo_manifest.json读取内容并上传草稿箱"""
import os, sys, json, time
import weibo_pipeline as wp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "weibo_manifest.json"), "r", encoding="utf-8") as f:
    articles = json.load(f)
print(f"载入 {len(articles)} 篇文章")

if not wp.wait_login(timeout=1800):
    print("仍未登录，退出")
    sys.exit(1)

results, draft_mode_ok = wp.phase_b(articles)
with open(os.path.join(BASE_DIR, "weibo_result.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nDONE")
