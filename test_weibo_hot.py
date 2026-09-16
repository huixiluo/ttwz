# -*- coding: utf-8 -*-
"""快速验证微博热搜获取"""
import hot_news_writer as hnw

session = hnw.get_visitor_session()
hot_list = hnw.get_hotsearch_list(session)
print(f"共获取 {len(hot_list)} 条微博热搜:")
for h in hot_list[:15]:
    cat = hnw.classify_hot(h)
    print(f"  [{h['rank']}] {h['title']}（{cat}, 热度{h.get('num', '?')}）")
