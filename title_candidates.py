# -*- coding: utf-8 -*-
"""爆款标题候选生成与人工挑选（上传前必经步骤）

流程（两个阶段）：
1. 生成候选：python title_candidates.py
   读取 output/batch_manifest.json，为每篇文章生成10个候选标题：
   - 编辑直写模式：存在 _manual_title_candidates.json 时直接使用其中的候选；
   - LLM模式：调用 generate_title_candidates() 基于最终正文生成（需 config.json）。
   候选保存到 output/title_candidates.json，并打印编号列表，暂停等待用户挑选。

2. 应用挑选：python title_candidates.py apply 1:3 2:1 3:0
   选择格式为 "文章序号:候选编号"，0 表示保持原标题，未指定的篇保持原标题。
   应用后更新 batch_manifest.json 的 title，并同步修补 HTML 中的 <title>/<h1>。

_manual_title_candidates.json 格式（编辑直写模式由助手人工编写）：
[
  {"keyword": "热搜词1", "candidates": ["标题一", "标题二", ...]},
  {"keyword": "热搜词2", "candidates": [...]},
  ...
]
"""
import os
import re
import sys
import json

import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 支持微博/编辑流程的 batch_manifest.json 与头条流程的 batch_manifest_tt.json
MANIFEST_CANDIDATES = [
    os.path.join(BASE_DIR, "output", "batch_manifest.json"),
    os.path.join(BASE_DIR, "output", "batch_manifest_tt.json"),
]
ROOT_MANIFEST_PATH = os.path.join(BASE_DIR, "batch_manifest.json")
CANDIDATES_PATH = os.path.join(BASE_DIR, "output", "title_candidates.json")
MANUAL_CANDIDATES_PATH = os.path.join(BASE_DIR, "_manual_title_candidates.json")


def detect_manifest_path():
    """自动检测当前批次清单：取存在文件中修改时间最新的一份"""
    existing = [p for p in MANIFEST_CANDIDATES if os.path.exists(p)]
    if not existing:
        raise FileNotFoundError(
            "未找到 " + " 或 ".join(MANIFEST_CANDIDATES) + "，请先运行批量生成"
        )
    newest = max(existing, key=lambda p: os.path.getmtime(p))
    if len(existing) > 1:
        print(f"[清单] 检测到多份清单，使用最新的一份：{newest}")
    return newest


def load_manifest():
    path = detect_manifest_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_candidate(title):
    """清洗并校验单个候选标题，返回 (合规标题, None) 或 (None, 不合规原因)"""
    title = hnw.clean_erhua((title or "").strip())
    if not title:
        return None, "空标题"
    if not hnw._is_three_part_title(title):
        return None, "非三段式（须恰好两个逗号）"
    if len(title) > 30:
        return None, f"超30字（{len(title)}字）"
    return title, None


def main_generate():
    articles = load_manifest()

    # 候选来源：编辑直写模式（人工候选文件）优先，否则LLM生成
    manual_map = {}
    llm_cfg = None
    if os.path.exists(MANUAL_CANDIDATES_PATH):
        with open(MANUAL_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            for m in json.load(f):
                if m.get("keyword"):
                    manual_map[m["keyword"]] = m.get("candidates", [])
        print(f"[模式] 编辑直写：检测到 {MANUAL_CANDIDATES_PATH}，使用人工候选")
    else:
        config = hnw.load_config()
        api_key = config.get("api_key")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise RuntimeError(
                "无 _manual_title_candidates.json 且 config.json 未配置API Key，无法生成候选标题。"
                "编辑直写模式请人工编写 _manual_title_candidates.json（格式见脚本头部说明）"
            )
        llm_cfg = {
            "api_key": api_key,
            "model": config.get("model", "deepseek-chat"),
            "api_url": config.get("api_url", "https://api.deepseek.com/v1/chat/completions"),
        }
        print("[模式] LLM生成：基于最终正文调用 generate_title_candidates()")

    print(f"共 {len(articles)} 篇文章，开始生成候选标题...")
    results = []
    for i, art in enumerate(articles, 1):
        print(f"\n[{i}/{len(articles)}] {art.get('category')} | {art.get('keyword')}")
        if manual_map:
            raw = manual_map.get(art.get("keyword"))
            if raw is None:
                raise KeyError(
                    f"文章[{art.get('keyword')}]在 _manual_title_candidates.json 中无对应候选，请补全该文件的候选"
                )
        else:
            print("  调用LLM生成10个候选标题...")
            raw = hnw.generate_title_candidates(
                art["article"], llm_cfg["api_key"], llm_cfg["model"], llm_cfg["api_url"]
            )

        # 清洗+校验过滤
        valid = []
        for c in raw:
            t, reason = sanitize_candidate(c)
            if t and t not in valid:
                valid.append(t)
            else:
                print(f"  [过滤] {c}（{reason or '重复'}）")
        if not valid:
            raise RuntimeError(f"文章[{art.get('keyword')}]无合规候选，请检查候选质量")
        print(f"  合规候选 {len(valid)} 个")

        results.append({
            "index": i,
            "category": art.get("category"),
            "keyword": art.get("keyword"),
            "current_title": art.get("title"),
            "candidates": valid,
        })

    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 打印供挑选的完整列表
    print("\n" + "=" * 60)
    print("候选标题列表（请挑选后再上传）")
    print("=" * 60)
    for r in results:
        print(f"\n【第{r['index']}篇】{r['category']} | {r['keyword']}")
        print(f"  [0] 保持原标题：{r['current_title']}")
        for j, c in enumerate(r["candidates"], 1):
            print(f"  [{j}] {c}（{len(c)}字）")
    print("\n挑选方式：在对话中确认后运行，例如：")
    print("  python title_candidates.py apply 1:3 2:1 3:0")
    print("（1:3 = 第1篇用候选3；0 = 保持原标题；未指定的篇保持原标题）")
    print(f"\n候选已保存：{CANDIDATES_PATH}")


def patch_html_title(html_path, new_title):
    """替换HTML中的 <title> 与 <h1> 文本，返回是否修改"""
    if not html_path or not os.path.exists(html_path):
        return False
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    html2 = re.sub(r"(<title>).*?(</title>)",
                   lambda m: m.group(1) + new_title + m.group(2), html, count=1)
    html2 = re.sub(r"(<h1[^>]*>).*?(</h1>)",
                   lambda m: m.group(1) + new_title + m.group(2), html2, count=1)
    if html2 == html:
        return False
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html2)
    return True


def main_apply(sel_args):
    manifest_path = detect_manifest_path()
    with open(manifest_path, "r", encoding="utf-8") as f:
        articles = json.load(f)
    if not os.path.exists(CANDIDATES_PATH):
        raise FileNotFoundError(f"未找到 {CANDIDATES_PATH}，请先运行 python title_candidates.py")
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        cand_list = json.load(f)

    # 解析选择参数：文章序号:候选编号
    selections = {}
    for s in sel_args:
        if not re.match(r"^\d+:\d+$", s):
            raise ValueError(f"选择格式错误：{s}（应为 文章序号:候选编号，如 1:3）")
        a, c = s.split(":")
        selections[int(a)] = int(c)

    changed = 0
    for r in cand_list:
        i = r["index"]
        pick = selections.get(i, 0)
        if pick == 0:
            print(f"[{i}] 保持原标题：{r['current_title']}")
            continue
        if pick < 1 or pick > len(r["candidates"]):
            raise IndexError(f"第{i}篇候选编号越界：{pick}（共{len(r['candidates'])}个候选）")
        new_title, reason = sanitize_candidate(r["candidates"][pick - 1])
        if not new_title:
            raise ValueError(f"第{i}篇选中候选不合规：{reason}")

        old_title = articles[i - 1].get("title")
        articles[i - 1]["title"] = new_title
        patched = patch_html_title(articles[i - 1].get("html_file"), new_title)
        print(f"[{i}] {old_title}")
        print(f"  -> {new_title}（{len(new_title)}字）  HTML标题{'已同步' if patched else '未改动/未找到'}")
        changed += 1

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    # 同步根目录副本（若使用的是 batch_manifest.json 且根目录副本存在，部分生成脚本会写两份清单）
    if manifest_path.endswith("batch_manifest.json") and os.path.exists(ROOT_MANIFEST_PATH):
        with open(ROOT_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n完成：{changed} 篇更换标题，清单已更新：{manifest_path}")
    print("可以继续执行批量上传（batch_upload.py / batch_upload_tt.py）")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "apply":
        if len(sys.argv) < 3:
            raise SystemExit("用法：python title_candidates.py apply 1:3 2:1 3:0（0=保持原标题）")
        main_apply(sys.argv[2:])
    else:
        main_generate()


if __name__ == "__main__":
    main()
