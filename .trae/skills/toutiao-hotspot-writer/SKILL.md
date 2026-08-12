---
name: "toutiao-hotspot-writer"
description: "Fetches Toutiao hot-board topics, classifies into entertainment/sports/society via keyword rules, fetches Toutiao article/comment text as source material, rewrites them into >600-word articles with three-part click-worthy titles (<=25 chars) via DeepSeek or direct editor authoring, polishes with a human-editor pass, fetches images via a 4-layer pipeline (Toutiao hot-board thumbnail -> Toutiao topic page body images -> Weibo topic post images -> Baidu Images fallback), and outputs HTML files. Supports batch generation and Toutiao draft upload."
---

# Toutiao Hotspot Writer

This skill fetches Toutiao hot-board topics, classifies them into 娱乐/体育/社会 three categories via keyword rules, fetches Toutiao topic article/comment text as source material, rewrites them into polished articles (>600 words) with three-part titles, applies a human-editor polish pass, fetches images via a 4-layer pipeline (Toutiao hot-board thumbnail -> Toutiao topic page images -> Weibo topic post images -> Baidu Images fallback), and outputs standalone HTML files. Supports batch generation and Toutiao draft upload.

## When to Invoke

**This is the DEFAULT skill for article generation.** When the user does not explicitly specify a platform (e.g. just says "生成文章", "批量生成上传草稿箱", "写几篇资讯"), this skill runs by default.

- User asks to generate rewritten articles from Toutiao hot trends
- User wants to produce entertainment/sports/society news content from current trends **without specifying a platform** (defaults to Toutiao hot-board)
- User asks to batch-generate multiple articles and upload to Toutiao drafts
- User explicitly mentions "头条" / "Toutiao"

## How It Works

The core pipeline has 7 steps:

1. **Fetch Toutiao hot-board**: Calls the official Toutiao PC hot-board API (`https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc`) to get ~50 trending topics. No login required. Topics are classified into 娱乐/体育/社会 three categories via built-in keyword rules (CATEGORY_KEYWORDS), with fallback to the Toutiao-provided `category` / `cluster_type` tags.
2. **List & confirm topics (MANDATORY pause)**: After fetching, the skill **must** list all candidate topics with their title, rank, heat value, and assigned category, then **stop and wait for user confirmation** before proceeding. The skill must NOT automatically start article generation. The user may approve the list as-is, remove specific topics, swap topics, or adjust category assignments. Only after the user explicitly confirms does the skill proceed to step 3. This is a hard gate — no downstream step (text fetch, authoring, images, HTML) may run before confirmation.
3. **Fetch Toutiao topic article/comment text**: For each confirmed topic, scrapes the Toutiao trending topic page (or related article URLs) to fetch up to 8 article snippets / hot comments as source material for article rewriting. Saved to `_toutiao_posts_raw.json`. This ensures article content is based on real Toutiao discussions, not fabricated.
4. **Article authoring (DeepSeek or direct editor)**: Two modes supported:
   - **DeepSeek mode**: Calls DeepSeek API to generate a three-part title (<=25 chars, two commas splitting three segments) + >600-word article based on the fetched post text. Prompt enforces: diverse openings (7 techniques), no AI flavor, no mechanical connectors, colloquial tone, neutral stance. Title is validated for three-part structure and retried if non-compliant.
   - **Direct editor mode** (when DeepSeek API is unavailable or balance insufficient): The assistant directly authors the article based on the fetched Toutiao topic text, following the same standards (three-part title, >600 words, diverse opening, no AI flavor, no erhua).
5. **Human-editor polish**: A second LLM pass (or editor pass) acts as a real human copy editor. Preserves all facts and core viewpoints, deletes empty pleasantries / mechanical connectors / flowery parallelism / repetitive conclusions / textbook-style endings, adjusts sentence rhythm, restores natural human writing feel. No meme-stacking, no forced slang, no fabricated stories.
6. **Image fetch & processing**: Uses a 4-layer priority pipeline via `fetch_images_unified()`: (1) Toutiao hot-board thumbnail (from the API `Image` field, normalized by `_extract_image_url()` to handle dict/str formats); (2) Toutiao topic detail page body images (regex-extracted from `toutiaoimg.com` URLs); (3) Weibo topic post images (visitor-session + `#keyword#` search via `/ajax/statuses/search`, extracts `pic_infos` original/largest/large URLs); (4) Baidu Images fallback. Each layer fills only the remaining count needed; final source composition is reported (e.g. `头条(1张) + 微博(3张) + 百度(1张)`). Applies Pillow processing (preserve original aspect ratio — no cropping, contrast/sharpness/color enhancement, unsharp mask, max width 1200px, JPEG quality 92). 5 images per article. Filters low-res images (width<500 or height<300).
7. **HTML output**: Embeds images as base64 into a styled HTML file. Saves to `./output/tt_hot_<category>_<index>_<timestamp>.html`. Cover images saved separately to `./output/covers/`.

## Usage

### Single article

```bash
python toutiao_hot_writer.py 娱乐   # Entertainment
python toutiao_hot_writer.py 体育   # Sports
python toutiao_hot_writer.py 社会   # Society
```

### Preview & confirm hot-board topics (MANDATORY before any generation)

```bash
python _preview_tt.py      # 9 topics (3 per category)
python _preview6_tt.py     # 6 topics (2 per category)
```

Lists topics, skipping previously used ones. The skill prints each topic's index, category, title, rank, and heat value, then **stops and waits for user confirmation**. The user can:

- Approve the list as-is → skill proceeds to generation
- Remove specific topics by index (e.g. "去掉第3条和第5条")
- Adjust category assignments (e.g. "第2条改成体育")
- Request more topics or a full re-fetch

**No article generation runs until the user explicitly confirms.** This is a hard gate enforced in both the SKILL instructions and the preview scripts. The confirmed list is saved to `_preview_tt_result.json` and used by all downstream steps.

### Fetch Toutiao topic article/comment text (source material)

```bash
python fetch_tt_posts.py
```

Fetches up to 8 article snippets / hot comments per topic from `_preview_tt_result.json`, saves to `_toutiao_posts_raw.json`. Article content is based on this real text, not fabricated.

### Batch generate articles

```bash
python batch_generate_tt.py    # 9 articles via DeepSeek API (needs config.json)
python generate_9_tt.py         # Editor-authored articles, NO DeepSeek needed, NO config.json needed
python generate_single_tt.py    # Single editor-authored article
```

`generate_9_tt.py` reads editor-authored articles from `_manual_articles_tt.json` (list format, recommended — self-contained with category/keyword) or `articles_9_tt.json` (dict format, needs `_preview_tt_result.json` for category). Does NOT call `load_config()` — uses sensible defaults (`output_dir=./output`, `image_count=5`). Applies `clean_erhua()` + three-part-title/word-count validation, saves covers via `save_cover_images()`.

Each article goes through: post text fetch (optional) -> authoring (DeepSeek or editor) -> human-editor polish -> image fetch -> HTML + cover save. Results saved to `./output/batch_manifest_tt.json`.

### Batch upload to Toutiao drafts

```bash
python batch_upload_tt.py          # Upload all articles in manifest
python batch_upload_tt.py 4        # Resume from 4th article (breakpoint recovery)
```

Reads `batch_manifest_tt.json`, uploads each article via `upload_visible.py` to the Toutiao creator platform draft box. Cover upload is enabled by default (SKIP_COVER=0). Supports breakpoint resume via command-line start index.

### Config

Edit `config.json` in the project root (create it if missing — it is not shipped with the skill; optional when using direct editor mode):

```json
{
  "api_key": "sk-xxx",
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "model": "deepseek-chat",
  "output_dir": "./output",
  "image_count": 5
}
```

When DeepSeek API key is missing or balance insufficient (402), the skill automatically falls back to direct editor authoring mode.

Field defaults (used when key absent): `model`=`deepseek-chat`, `api_url`=`https://api.deepseek.com/v1/chat/completions`, `output_dir`=`./output`, `image_count`=`3`. Note: the image-layout algorithm and all rules in this doc are designed around **5 images** — set `image_count: 5` explicitly to match.

## Output Requirements (enforced in prompt and code)

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
11. **Erhua post-processing**: `clean_erhua()` function removes any erhua suffixes from both title and article (24 replacement groups + regex fallback, excluding valid 儿 words like 儿女/儿童/儿子).

### Article (>600 words, strictly enforced)

- **>600 words (hard requirement)**, ideal range 650-850 words, 6-8 paragraphs, at least 6 (each <=150 chars);
- Article content must be based on fetched Toutiao topic article/comment text, not fabricated;
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
- Ban erhua (儿化音): never use 事儿/点儿/地儿/哥们儿/玩意儿. Use standard forms. Enforced both in prompt and via `clean_erhua()` post-processing.
- **Code-level double insurance**: `clean_erhua()` runs after both rewrite and polish — replaces via `_ERHUA_MAP` (long-match first, 24 groups), then regex strips residual `汉字+儿` suffixes (excluding legitimate word-initial 儿 like 儿女/儿童/儿子).

### Human-Editor Polish (second pass)

After the initial draft, `polish_article()` runs a second DeepSeek pass (or editor pass) as a real human copy editor:

- **Preserve**: all original facts, core viewpoints. No tampering, deletion, or fabrication;
- **Delete**: empty pleasantries, mechanical connectors, flowery parallelism, repetitive conclusions, textbook-style endings;
- **Adjust**: sentence length rhythm, natural logical transitions;
- **Allow**: slight imperfections to restore natural human writing feel;
- **Ban**: meme-stacking, forced slang, fabricated stories/details, template-style writing;
- **Word count**: polished article must remain >600 words; if deletion would drop below 600, supplement content to maintain length;
- Keep the original overall tone and paragraph structure. Only polish the prose level.

### Images

- 5 images per article. Sourcing uses a **4-layer priority pipeline** via `fetch_images_unified()` — each layer fills only the remaining count needed, shortfalls fall through to the next layer:
  1. **Toutiao hot-board thumbnail** (layer 1) — the `Image` field from the hot-board API response. `_extract_image_url()` normalizes the field which may be a dict (`{url, url_list, uri}`) or a string; falls back to `url_list[0]` then `uri`-composed URL. This image is directly tied to the topic.
  2. **Toutiao topic detail page body images** (layer 2) — regex-extracts `toutiaoimg.com` image URLs from the topic page HTML. Fills remaining slots after layer 1.
  3. **Weibo topic post images** (layer 3) — `get_weibo_session()` simulates the Weibo visitor system (SUB cookie, no login), then `fetch_images_from_weibo()` searches `#keyword#` via `/ajax/statuses/search` and extracts `pic_infos` URLs (priority: `original` -> `largest` -> `large`). Weibo topic posts are highly relevant since the same hot topic often trends on both platforms. Layer skipped silently if visitor-session fails.
  4. **Baidu Images fallback** (layer 4) — when all above layers are still short of `count`. Uses real image-content search, prioritizes `middleURL`/`thumbURL` over encrypted `objURL`.
- **Source reporting**: the final composition is returned as a string like `头条(1张) + 微博(3张) + 百度(1张)`, logged and saved to manifest `image_source` field for traceability.
- Filter low-res images: skip images <8KB or width<500 or height<300 (ensures people in images are clearly visible);
- Preserve original aspect ratio — no cropping (keeps full image content);
- Filters (contrast +12%, sharpness +30%, color +8%, unsharp mask 90%);
- Max width 1200px (downscale only, never upscale), JPEG quality 92, base64-encoded;
- 3 cover images saved separately as JPEG files to `./output/covers/` — **uploaded by default** (SKIP_COVER=0);
- Dynamic layout (5 images cap): 1 image after paragraph 1, then fill 2-image groups "every 2 paragraphs" forward; when the last group leaves >2 pure-text paragraphs at the tail, shift the last 2-image group back to leave exactly 2 paragraphs at the end — ensures no 3–4 paragraph long text tail.

## Toutiao Hot-Board API

Toutiao provides an official PC hot-board endpoint (no login required, direct HTTP GET with proper headers):

| API | Endpoint |
|-----|---------|
| 综合热榜 (Unified Hot Board) | `https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc` |

Returns a JSON array under `data` with ~50 items. Each item contains: `Rank` (rank), `Title` (title), `HotValue` (heat value), `Url` (topic detail URL), `Image` (thumbnail), `ClusterId` (topic ID), `cluster_type`, etc. `_parse_tt_hot_list()` normalizes them and classifies each item into 娱乐/体育/社会 via two-layer strategy:

1. **Primary**: keyword matching against CATEGORY_KEYWORDS (entertainment/sports/society keyword groups, long-match-first, score-based classification, highest-score category wins).
2. **Fallback**: map `cluster_type` / URL `category_name` params to category when keyword match is ambiguous or ties.

Cross-category deduplication via `used_titles` set ensures no duplicate topics across categories.

If the official hot-board API returns an internal error (system maintenance or rate limit), the skill automatically falls back to scraping the Toutiao PC homepage hot-board DOM section as a same-source alternative (20-min update frequency, no additional auth needed).

## Toutiao Topic Article/Comment Text Fetch

`fetch_tt_posts.py` fetches Toutiao topic article snippets and hot comments as source material:

1. Reads `_preview_tt_result.json` for confirmed topics.
2. Opens each topic's `Url` from the hot-board response and scrapes:
   - Topic page headline article abstract / body snippets (up to 5);
   - Hot comment section text (up to 3 comments);
   - Related article titles + abstracts from the topic page.
3. Extracts up to 8 text fragments per topic: source, text, timestamp.
4. Saves to `_toutiao_posts_raw.json`.
5. Article content is authored based on this real Toutiao discussion text, ensuring no fabrication.

`fetch_toutiao_posts_text()` in `toutiao_hot_writer.py` is the core function. It handles Toutiao topic page rendering (fallback to lightweight requests + regex extraction when full browser render is unavailable) and text extraction from abstract fields and comment nodes.

## Toutiao Draft Upload

The skill includes `upload_visible.py` for uploading generated articles to the Toutiao creator platform draft box. It uses DrissionPage to drive a real Chrome browser (non-headless).

### Upload Flow

1. **Login**: Load cookies from `toutiao_cookies.json` and navigate to `mp.toutiao.com`.
2. **Create new article**: Open the publish page, wait for the ProseMirror editor to mount.
3. **Fill title**: Use native `value setter` + `input`/`change` events to trigger React state update (DrissionPage's `input()` doesn't work for React-controlled title textarea).
4. **Upload body images**: Two-stage approach:
   - Stage 1: Upload all images one-by-one by pasting Blob via `ClipboardEvent('paste')`, capturing returned server URLs.
   - Stage 2: Set all content (text + images) at once via ProseMirror `view.dispatch()` API with properly structured image nodes.
5. **Upload covers**: By default `SKIP_COVER=0` uploads 3 covers via file input. Set `SKIP_COVER=1` to skip.
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

Dynamic layout via `calc_image_layout(total_paragraphs, num_images=5)` — respects the 5-image hard cap, guarantees **at most 2–3 pure-text tail paragraphs** (priority is to keep middle pure-text gaps ≤3 paragraphs to avoid long unbroken text stretches):

1. **Fixed header**: 1 image after paragraph 1 (uses 1 image, 4 remaining → 2 groups of 2 for 5 images total; or 1 group of 2 for 3-image fallback).
2. **Uniform even-spacing**: Remaining 2-image groups are placed at equal-step positions between the header image (pos=1) and the desired tail anchor. The default tail anchor is `total_paragraphs - 2` (keeping exactly 2 pure-text trailing paragraphs).
3. **Gap≤3 priority with tail relaxation**: The algorithm evaluates two candidate layouts (tail=2 and tail=3) and selects the one that first achieves a **maximum pure-text gap of ≤3 paragraphs between adjacent image groups**. Only when gap≤3 is satisfied for both candidates does it prefer the layout with the shorter tail.
4. **Edge trimming**: If a 2-image group would land flush against the last paragraph (tail < 1), it is removed to prevent the image from touching the article end.

### Batch Upload with Breakpoint Recovery

`batch_upload_tt.py` reads `batch_manifest_tt.json` and uploads each article sequentially. Supports a command-line start index for resuming after interruptions:

```bash
python batch_upload_tt.py 4   # Resume from 4th article
```

Each article upload runs as a subprocess with a 180s timeout. Logs are written to `batch_upload_tt.log` with timestamps.

## Dependencies

- Python 3.10+
- `requests`, `Pillow`, `DrissionPage`
- DeepSeek API key (in config.json) — **optional**, falls back to direct editor mode when unavailable
- Toutiao cookies (in toutiao_cookies.json, for upload only)
- Network access to: toutiao.com, api.deepseek.com (optional), image.baidu.com, mp.toutiao.com, weibo.com (for image layer 3)

## Error Handling

- If Toutiao hot-board API returns internal error / rate limit: automatically falls back to Toutiao PC homepage hot-board DOM scraping (same-source alternative, 20-min update cycle).
- **Toutiao hot-board `Image` field type inconsistency**: the API sometimes returns `Image` as a dict (`{url, url_list, uri, width, height}`) instead of a plain string, which breaks `startswith("http")` checks and slice operations. Fixed: `_extract_image_url()` normalizes dict/str/empty inputs into a usable URL string (priority: `url` -> `url_list[0].url` -> `uri`-composed URL).
- If Toutiao topic page images are insufficient: falls through to Weibo topic post images (layer 3), then Baidu Images (layer 4).
- **Weibo visitor-session failure**: if `get_weibo_session()` cannot obtain a SUB cookie (network issue or Weibo interface change), layer 3 is skipped silently and the pipeline continues to Baidu. No hard failure.
- **Weibo topic coverage gap**: not every Toutiao hot topic has matching Weibo posts. For society/news topics with no Weibo presence, the pipeline naturally falls through to Baidu. This is expected behavior, not an error.
- If DeepSeek API fails (402 = insufficient balance, missing key): falls back to direct editor authoring mode.
- If title fails three-part validation: automatically retries once.
- If batch upload stalls: use `python batch_upload_tt.py <start_index>` to resume.
- If cover upload fails: article content is still saved; covers can be manually added later. Set `SKIP_COVER=1` to skip cover upload entirely.
- **Stale temp images**: `upload_visible.py` saves body images to `output/tmp/body_img_N.jpg` before uploading. If these files persist from a previous article, they will be reused by mistake, causing the wrong images to appear in the new article. Fixed: all `body_img_*` files are cleared before each upload, forcing fresh extraction from the current article's base64 data.
- **Baidu image encrypted objURL**: Some Baidu image results return encrypted `objURL` that cannot be directly downloaded. Fixed: prioritize `middleURL`/`thumbURL` (always accessible) over `objURL`.
