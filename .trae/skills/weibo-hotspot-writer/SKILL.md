---
name: "weibo-hotspot-writer"
description: "Fetches Weibo trending topics by category (entertainment/sports/society), rewrites them into ~600-word articles with three-part click-worthy titles (<=25 chars) via DeepSeek, polishes with a human-editor pass, fetches images from Weibo original posts (Baidu fallback), and outputs HTML files. Supports batch generation and Toutiao draft upload."
---

# Weibo Hotspot Writer

This skill fetches Weibo category hot searches, rewrites them into polished articles with three-part titles, applies a human-editor polish pass, fetches images from Weibo original posts, and outputs standalone HTML files. Supports batch generation and Toutiao draft upload.

## When to Invoke

- User asks to generate rewritten articles from Weibo hot trends
- User wants to produce entertainment/sports/society news content from current trends
- User asks to batch-generate multiple articles and upload to Toutiao drafts

## How It Works

The core pipeline has 5 steps:

1. **Fetch Weibo category hot search**: Simulates the Weibo visitor system to get a SUB cookie, then calls official category APIs (`/ajax/statuses/entertainment`, `/ajax/statuses/sport`, `/ajax/statuses/social`) to get 50 trending topics per category. No login required.
2. **DeepSeek rewrite**: Calls DeepSeek API to generate a three-part title (<=25 chars, two commas splitting three segments) + ~600-word article. Prompt enforces: diverse openings (7 techniques), no AI flavor, no mechanical connectors, colloquial tone, neutral stance. Title is validated for three-part structure and retried if non-compliant.
3. **Human-editor polish**: A second LLM pass acts as a real human copy editor. Preserves all facts and core viewpoints, deletes empty pleasantries / mechanical connectors / flowery parallelism / repetitive conclusions / textbook-style endings, adjusts sentence rhythm, restores natural human writing feel. No meme-stacking, no forced slang, no fabricated stories.
4. **Image fetch & processing**: Prioritizes Weibo original post images (via `/ajax/statuses/search` API, extracts `pic_infos` large/largest/original URLs), falls back to Baidu Images if insufficient. Applies Pillow processing (16:9 center crop, contrast/sharpness/color enhancement, unsharp mask). 5 images per article.
5. **HTML output**: Embeds images as base64 into a styled HTML file. Saves to `./output/hot_<category>_<index>_<timestamp>.html`. Cover images saved separately to `./output/covers/`.

## Usage

### Single article

```bash
python hot_news_writer.py 娱乐   # Entertainment
python hot_news_writer.py 体育   # Sports
python hot_news_writer.py 社会   # Society
```

### Preview category hot searches (no generation)

```bash
python _preview.py
```

Lists 6 topics (2 per category), skipping previously used ones. User confirms before generation.

### Batch generate 6 articles (2 entertainment + 2 sports + 2 society)

```bash
python batch_generate.py
```

Each article goes through: DeepSeek rewrite -> human-editor polish -> image fetch -> HTML + cover save. Results saved to `./output/batch_manifest.json`.

### Batch upload to Toutiao drafts

```bash
python batch_upload.py          # Upload all articles in manifest
python batch_upload.py 4        # Resume from 4th article (breakpoint recovery)
```

Reads `batch_manifest.json`, uploads each article via `upload_visible.py` to the Toutiao creator platform draft box. Cover upload is skipped by default (set `SKIP_COVER=0` to enable). Supports breakpoint resume via command-line start index.

### Config

Edit `config.json` in the project root:

```json
{
  "api_key": "sk-xxx",
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "model": "deepseek-chat",
  "output_dir": "./output",
  "image_count": 5
}
```

## Output Requirements (enforced in prompt)

### Title - Three-part structure (<=25 chars, strictly enforced)

1. **Must be three-part**: title consists of three short phrases separated by Chinese commas. Exactly two commas, three segments. Example: "明星哭穷上热搜，网友不买账，这届观众清醒了". Single-segment or two-segment titles are rejected.
2. <=25 chars (including punctuation), semantically complete, no half-sentences;
3. Choose from two structures based on the topic content:
   - **Structure A (event + detail + suspense)**: state the event, add a key detail, end with suspense. Preferred when the topic has dramatic details.
   - **Structure B (phenomenon + conflict + question)**: describe the phenomenon, point out the conflict, end with a question. Preferred when the topic involves controversy or contrast.
4. Each segment <=8 chars, punchy rhythm, colloquial, no written-style tone;
5. Create suspense/conflict/contrast; may use questions, numbers, contrast, emotional words. No clickbait scam;
6. No low-quality clickbait words;
7. Title must match content; no fabricating unverified facts;
8. Neutral and objective. No favoring or naming specific persons;
9. **Self-check**: after writing, verify the title has exactly two commas and three segments. If not, rewrite.
10. **Code-level validation**: `_is_three_part_title()` checks comma count == 2; non-compliant titles trigger one retry.

### Article (~600 words)

- ~600 words, 5-6 paragraphs (each <=150 chars);
- Positive tone, reader-resonant, ends with a comment-prompting hook;
- Neutral and objective, no favoring or attacking specific persons;
- Supplement background info or extended content to add depth.

### Opening - Diverse & natural (strictly enforced)

**Banned opening patterns**:
- "刷到/看到/点开 + 热搜/榜单/话题" patterns;
- "朋友圈里/群里/评论区" patterns;
- Self-referencing rank ("热搜第X位");
- "近日/近日来/近日，一则..." news-template patterns;
- "话说回来/闲来无事" filler.

**7 opening techniques** (choose the most fitting one per article, avoid repeating):
- Scene cut-in: a concrete life scene or image;
- Detail cut-in: start from the most gripping detail/quote/action;
- Question cut-in: a thought-provoking question;
- Opinion cut-in: lead with a judgment or stance;
- Contrast cut-in: past-vs-present or appearance-vs-reality;
- Story cut-in: natural storytelling opening;
- Emotion cut-in: directly state a feeling for empathy.

Must grab the reader within the first three sentences. No roundabout padding.

### Style (no AI flavor - strictly enforced)

- Ban mechanical connectors: 首先/其次/最后/总之/综上所述/不难看出/值得一提的是;
- Ban parallel-clause stacking: 是...也是...更是... / 不仅...而且...还...;
- Ban empty adjective stacking: 令人深思、发人深省、意义深远;
- Ban ending every paragraph with a summary sentence;
- Use colloquial language, like chatting with a friend;
- Vary sentence length. Mix long and short;
- Personal perspective and emotion allowed: 说实话/老实讲/说起来;
- Ban erhua (儿化音): never use 事儿/点儿/地儿/哥们儿/玩意儿. Use standard forms.

### Human-Editor Polish (second LLM pass)

After the initial draft, `polish_article()` runs a second DeepSeek pass as a real human copy editor:

- **Preserve**: all original facts, core viewpoints. No tampering, deletion, or fabrication;
- **Delete**: empty pleasantries, mechanical connectors, flowery parallelism, repetitive conclusions, textbook-style endings;
- **Adjust**: sentence length rhythm, natural logical transitions;
- **Allow**: slight imperfections to restore natural human writing feel;
- **Ban**: meme-stacking, forced slang, fabricated stories/details, template-style writing;
- Keep the original overall tone and paragraph structure. Only polish the prose level.

### Images

- 5 images per article, sourced from Weibo original posts first (via `/ajax/statuses/search` -> `pic_infos` -> large/largest/original URL), Baidu Images as fallback;
- 16:9 center crop with filters (contrast +12%, sharpness +25%, color +8%, unsharp mask);
- Max width 800px, JPEG quality 88, base64-encoded;
- 3 cover images saved separately as JPEG files to `./output/covers/`;
- Dynamic layout: 1 image after paragraph 1, then 2 images every 2 paragraphs (after 3/5/7/9..., only if at least 2 paragraphs remain after), no images if fewer than 2 paragraphs left at the end.

## Category Hot Search API

Weibo provides official category hot search endpoints (no login required, accessible via visitor session):

| Category | API Endpoint |
|----------|-------------|
| 娱乐 (Entertainment) | `https://weibo.com/ajax/statuses/entertainment` |
| 体育 (Sports) | `https://weibo.com/ajax/statuses/sport` |
| 社会 (Society) | `https://weibo.com/ajax/statuses/social` |

Each returns `data.band_list` with ~50 items. `_parse_band_list()` normalizes them (skips ads, extracts word/rank/num/category). Cross-category deduplication via `used_titles` set ensures no duplicate topics across categories.

## Toutiao Draft Upload

The skill includes `upload_visible.py` for uploading generated articles to the Toutiao creator platform draft box. It uses DrissionPage to drive a real Chrome browser (non-headless).

### Upload Flow

1. **Login**: Load cookies from `toutiao_cookies.json` and navigate to `mp.toutiao.com`.
2. **Create new article**: Open the publish page, wait for the ProseMirror editor to mount.
3. **Fill title**: Use native `value setter` + `input`/`change` events to trigger React state update (DrissionPage's `input()` doesn't work for React-controlled title textarea).
4. **Upload body images**: Two-stage approach:
   - Stage 1: Upload all images one-by-one by pasting Blob via `ClipboardEvent('paste')`, capturing returned server URLs.
   - Stage 2: Set all content (text + images) at once via ProseMirror `view.dispatch()` API with properly structured image nodes.
5. **Skip or upload covers**: By default `SKIP_COVER=1` skips cover upload. Set `SKIP_COVER=0` to upload 3 covers via file input.
6. **Verify**: Check draft list for the article.

### Critical: Image Node Attribute

The Toutiao ProseMirror schema's `image` node stores the URL inside a nested `data` object attribute, **NOT** a top-level `src`:

```json
{
  "type": "image",
  "attrs": {
    "data": {
      "url": "https://image-tt-private.toutiao.com/...",
      "icUri": "https://image-tt-private.toutiao.com/...",
      "caption": "图片来源于网络"
    }
  }
}
```

### Image Layout

Dynamic layout via `calc_image_layout(total_paragraphs)`:
- 1 image fixed after paragraph 1;
- Then 2 images after every 2 paragraphs (3, 5, 7, 9...), but only when at least 2 paragraphs remain after that point (ensures the last 1–2 paragraphs are pure text, no tail-end orphan images);
- Remaining unused images (if any) are appended at the end as a fallback.

Examples:
| Total paragraphs | Layout dict | Total images placed |
|---|---|---|
| 3 | {1: 1} | 1 |
| 5 | {1: 1, 3: 2} | 3 |
| 7 | {1: 1, 3: 2, 5: 2} | 5 |
| 8 | {1: 1, 3: 2, 5: 2} | 5 |
| 9+ | every +2 paragraphs adds +2 images | increases by 2 |

### Batch Upload with Breakpoint Recovery

`batch_upload.py` reads `batch_manifest.json` and uploads each article sequentially. Supports a command-line start index for resuming after interruptions:

```bash
python batch_upload.py 4   # Resume from 4th article
```

Each article upload runs as a subprocess with a 180s timeout. Logs are written to `batch_upload.log` with timestamps.

## Dependencies

- Python 3.10+
- `requests`, `Pillow`, `DrissionPage`
- DeepSeek API key (in config.json)
- Toutiao cookies (in toutiao_cookies.json, for upload only)
- Network access to: weibo.com, api.deepseek.com, image.baidu.com, mp.toutiao.com

## Error Handling

- If Weibo visitor system fails to get SUB cookie: raises RuntimeError.
- If Weibo original post images are insufficient: falls back to Baidu Images.
- If DeepSeek API fails: check API key in config.json (402 = insufficient balance).
- If title fails three-part validation: automatically retries once.
- If batch upload stalls: use `python batch_upload.py <start_index>` to resume.
- If cover upload fails: article content is still saved; covers can be manually added later.
