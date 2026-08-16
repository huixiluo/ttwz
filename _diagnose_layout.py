# -*- coding: utf-8 -*-
"""诊断新布局算法（强制重新加载模块）"""
import sys
import importlib.util

spec = importlib.util.spec_from_file_location(
    "hnw", r"c:\Users\huixi\Documents\trae_projects\ttwz\hot_news_writer.py"
)
hnw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hnw)
_calc = hnw._calc_image_layout


def analyze(n, layout):
    sorted_pos = sorted(layout.keys())
    gaps = []
    for a, b in zip(sorted_pos, sorted_pos[1:]):
        gaps.append(b - a - 1)
    tail = n - sorted_pos[-1] if sorted_pos else 0
    return gaps, tail

print("新算法（均匀分布，强制重载模块）：")
print("| 段数 | Layout | 配图数 | 各图组间纯文字段(空档) | 尾段 | 中间最大空档 |")
print("|---|---|---|---|---|---|")
for n in range(3, 15):
    l = _calc(n, 5)
    total = sum(l.values())
    gaps, tail = analyze(n, l)
    max_gap = max(gaps) if gaps else 0
    flag = ""
    if max_gap > 3:
        flag = "  ⚠️中间"+str(max_gap)+"段无配图"
    print(f"| {n} | {l} | {total} | {gaps} | {tail} | {max_gap}{flag} |")
