---
name: "weibo-hotspot-writer"
description: "Fetches a Weibo trending topic, rewrites it into a ~600-word article with a click-worthy title (≤25 chars) via DeepSeek, fetches and processes images from Baidu, and outputs an HTML file. Invoke when user wants to generate a rewritten hot news article from Weibo trends, or mentions 微博热搜/热点改写/爆款文章生成."
---

# Weibo Hotspot Writer

This skill rewrites a Weibo trending topic into a polished, original article with images, output as a standalone HTML file.

## When to Invoke

- User asks to generate a rewritten article from Weibo hot trends
- User mentions "微博热搜改写", "热点文章生成", "爆款文章"
- User wants to produce entertainment/sports/society news content from current trends
- User asks to run the daily hot news generation task

## How It Works

The skill is backed by a Python script `hot_news_writer.py` located in the project root. It performs 5 steps:

1. **Fetch Weibo hot search**: Simulates the Weibo visitor system to get a SUB cookie, then parses `s.weibo.com/top/summary` HTML to extract 50 trending topics.
2. **Category filter**: Matches topics against keyword rules to pick the top-ranked item in the requested category (娱乐/体育/社会).
3. **DeepSeek rewrite**: Calls DeepSeek API (OpenAI-compatible) to generate a click-worthy title (≤25 chars) + ~600-word article. Prompt enforces: no AI flavor, no mechanical connectors, colloquial tone, neutral stance (no bias toward specific persons), no fabricated assumptions.
4. **Image fetch & processing**: Searches Baidu Images for the keyword, downloads 3 images, and applies Pillow processing (16:9 center crop, contrast/sharpness/color enhancement, unsharp mask).
5. **HTML output**: Embeds images as base64 into a styled HTML file, inserting one image every two paragraphs. Saves to `./output/hot_<category>_<timestamp>.html`.

## Usage

### Run via command line

```bash
python hot_news_writer.py 娱乐   # Entertainment
python hot_news_writer.py 体育   # Sports
python hot_news_writer.py 社会   # Society
```

### Config

Edit `config.json` in the project root:

```json
{
  "api_key": "sk-xxx",
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "model": "deepseek-chat",
  "output_dir": "./output",
  "image_count": 3
}
```

### Preview output

Start a local HTTP server to preview generated HTML files:

```bash
python -m http.server 8000 --directory output
```

Then open `http://localhost:8000/` in a browser to see the file list, or directly open a specific HTML file URL.

## Output Requirements (enforced in prompt)

### Title (3-segment style, 鈮?5 chars)

1. Must be a **3-segment click-worthy title**, 鈮?5 chars (including punctuation);
2. Three-segment structure: the title consists of three short phrases separated by commas, forming a rhythmic "event + detail + suspense" or "phenomenon + conflict + question" structure. Examples: "绁ㄦ埧鐮村崄浜匡紝鍙ｇ鍗翠袱鏋侊紝杩欑墖鍒板簳鍊间笉鍊?, "鎻愬悕鍚嶅崟涓€鍑猴紝鑰佹垙楠ㄩ綈鑱氾紝璋佽兘绗戝埌鏈€鍚?;
3. Each segment short and punchy, three segments build up progressively, the last segment creates suspense or poses a question to make people want to click;
4. Can use numbers, contrast, emotional words, but no clickbait scam;
5. Colloquial, like something a friend would say, no written-style tone;
6. Do not use low-quality clickbait words like "闇囨儕锛?"閫熺湅锛?"绐佸彂锛?;
7. Title must match article content, no mismatch;
8. No fabricating or implying unverified facts, no misleading hypothetical statements (e.g. "鏌愭煇娌℃嬁濂栵紵" "鏌愭煇瑕侀€€鍑猴紵"), questions must be based on publicly verified facts only;
9. Title must not favor or name a specific person 鈥?if the article doesn't favor one person, the title shouldn't focus on one person either. Cut in from the event as a whole or from a group perspective, stay neutral and objective.
### Article (~600 words)

- ~600 words, 4-5 paragraphs (each ≤150 chars);
- Positive tone, reader-resonant, ends with a comment-prompting hook;
- Neutral and objective, no favoring or attacking specific persons, present everyone equally when multiple people are involved;
- Supplement background info (causes, context) or extended content (similar cases) to add depth.

### Style (no AI flavor — strictly enforced)

- Ban mechanical connectors: 首先/其次/最后/总之/综上所述/不难看出/值得一提的是;
- Ban parallel-clause stacking: 是...也是...更是... / 不仅...而且...还...;
- Ban empty adjective stacking: 令人深思、发人深省、意义深远;
- Ban ending every paragraph with a summary sentence;
- Use colloquial language, like chatting with a friend — slang, proverbs, metaphors are welcome;
- Vary sentence length — mix long and short, occasionally use a very short sentence for rhythm;
- Personal perspective and emotion allowed: 说实话/老实讲/这事儿说起来;
- Do not start with 近日/近日来/近日，一则... — use a more immersive opening.

### Images

- 3 images, one every two paragraphs;
- 16:9 center crop with filters applied (contrast +12%, sharpness +25%, color +8%, unsharp mask);
- Clear and visible, max width 800px, JPEG quality 88.

## Scheduled Task

A TRAE scheduled task "微博热搜改写-每日产出" runs daily at 12:00 (Asia/Shanghai) to auto-generate an entertainment article. The task prompt runs the script and displays the title + article content to the user.

## Dependencies

- Python 3.10+
- `requests`, `Pillow`
- DeepSeek API key (in config.json)
- Network access to: s.weibo.com, api.deepseek.com, image.baidu.com

## Error Handling

- If Weibo visitor system fails to get SUB cookie: retry once.
- If Baidu image search returns too few images: article still generates with whatever images are available.
- If DeepSeek API fails: check API key in config.json and network connectivity.
