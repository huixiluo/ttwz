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
3. **DeepSeek rewrite**: Calls DeepSeek API (OpenAI-compatible) to generate a three-segment click-worthy title (≤25 chars, 事件+细节+悬念 or 现象+冲突+疑问) + ~600-word article. Prompt enforces: no AI flavor, no mechanical connectors, colloquial tone, neutral stance (no bias toward specific persons), no fabricated assumptions.
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

### Title (≤25 chars, three-segment click-worthy)

The title uses a three-segment structure separated by commas, auto-selecting between two formats based on the content:

- **事件+细节+悬念**: For news with clear event progression — summarize event, add detail, create suspense.
- **现象+冲突+疑问**: For social phenomena or controversial topics — describe phenomenon, create conflict/contrast, end with a question.

Rules:
1. Three segments total ≤25 chars (including two commas), each segment must be a semantically complete phrase;
2. Colloquial, like something a friend would say, no written-style tone;
3. Do not use low-quality clickbait words like "震惊！""速看！""突发！";
4. Title must match article content, no mismatch;
5. No fabricating or implying unverified facts, no misleading hypothetical statements, questions must be based on publicly verified facts only;
6. Title must not favor or name a specific person — stay neutral and objective.

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
- Personal perspective and emotion allowed: 说实话/老实讲/说起来;
- Do not start with 近日/近日来/近日，一则... — use a more immersive opening;
- Ban erhua (儿化音): never use 事儿/点儿/地儿/哥们儿/玩意儿 — use standard forms like 这件事/一点/地方/朋友/东西.

### Images

- 3 images, one every two paragraphs;
- 16:9 center crop with filters applied (contrast +12%, sharpness +25%, color +8%, unsharp mask);
- Clear and visible, max width 800px, JPEG quality 88.

## Toutiao Draft Upload

The skill includes `upload_visible.py` for uploading generated articles to the Toutiao creator platform draft box. It uses DrissionPage to drive a real Chrome browser (non-headless) for completing the full publishing flow.

### Upload Flow

1. **Login**: Load cookies from `toutiao_cookies.json` and navigate to `mp.toutiao.com`.
2. **Create new article**: Open the publish page with a cache-busting timestamp, wait for the ProseMirror editor to mount.
3. **Fill title**: Input the article title (≤30 chars) into the title textarea and trigger auto-save.
4. **Upload body images**: For each image, paste a Blob via `ClipboardEvent('paste')` to trigger the editor's built-in upload handler, then capture the returned server URL (`image-tt-private.toutiao.com`). Deduplicate by URL path.
5. **Set editor content via ProseMirror API**: Build the document JSON (paragraphs + image nodes) and dispatch a transaction through `view.dispatch(view.state.tr.replaceWith(...))` to ensure internal state syncs with the DOM. Setting `innerHTML` directly does NOT update ProseMirror state and causes images to be lost on save.
6. **Upload 3 covers**: Select 3-image cover mode, trigger the `.article-cover-add` button, and input each cover file via the file input.
7. **Verify**: Navigate to the draft list and confirm the article appears.

### Critical: Image Node Attribute

The Toutiao ProseMirror schema's `image` node stores the URL inside a nested `data` object attribute, **NOT** a top-level `src`:

```json
{
  "type": "image",
  "attrs": {
    "data": {
      "url": "https://image-tt-private.toutiao.com/...",
      "icUri": "https://image-tt-private.toutiao.com/...",
      "caption": "图片来源于网络",
      "link": "",
      "ic": false,
      "naturalHeight": 0,
      "naturalWidth": 0,
      "srcType": "",
      "captionLenErr": false,
      "needCheck": false
    }
  }
}
```

Setting `attrs.src` instead of `attrs.data.url` produces an image node whose URL is empty when serialized for the save API, so the draft appears to have no images. Always inspect `schema.nodes.image.spec.attrs` and match the actual attribute shape.

### Image Layout

Enforced via `IMAGE_LAYOUT = {1: 1, 3: 2, 5: 2}` — 1 image after paragraph 1, 2 after paragraph 3, 2 after paragraph 5 (5 images total).

### Debugging

- `debug.log` records every step with timestamps for post-run diagnosis.
- A network interceptor injected into the page captures all POST bodies, allowing verification that the `/mp/agw/article/publish` request actually contains image URLs.
- The ProseMirror `view` object is located by traversing React Fiber from the editor DOM element (the view is not exposed on `window`).

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
