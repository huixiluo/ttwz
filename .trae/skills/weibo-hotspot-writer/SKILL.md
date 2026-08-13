---
name: "weibo-hotspot-writer"
description: "Fetches Weibo trending topics by category (entertainment/sports/society), fetches Weibo original post text as source material, rewrites them into >600-word articles with three-part click-worthy titles (<=25 chars) via DeepSeek or direct editor authoring, polishes with a human-editor pass, fetches images from Weibo original posts (Baidu fallback), and outputs HTML files. Supports batch generation and Toutiao draft upload."
---

# Weibo Hotspot Writer

This skill fetches Weibo category hot searches, fetches original post text as source material, rewrites them into polished articles (>600 words) with three-part titles, applies a human-editor polish pass, fetches images from Weibo original posts, and outputs standalone HTML files. Supports batch generation and Toutiao draft upload.

## When to Invoke

**This skill only runs when the user EXPLICITLY specifies Weibo as the source.** When the platform is not specified, the default skill (`toutiao-hotspot-writer`) runs instead.

- User explicitly asks to generate rewritten articles from **Weibo** hot trends
- User explicitly mentions "微博" / "Weibo" as the data source
- User wants to produce entertainment/sports/society news content from **Weibo** trends (not generic "trends" — that defaults to Toutiao)

## How It Works

The core pipeline has 7 steps:

1. **Fetch Weibo category hot search**: Simulates the Weibo visitor system to get a SUB cookie, then calls official category APIs (`/ajax/statuses/entertainment`, `/ajax/statuses/sport`, `/ajax/statuses/social`) to get 50 trending topics per category. No login required.
2. **Fetch Weibo original post text**: Calls `/ajax/statuses/search` API to fetch original post text (up to 8 posts per topic) as source material for article rewriting. Saved to `_weibo_posts_raw.json`. This ensures article content is based on real Weibo posts, not fabricated.
3. **Article authoring (DeepSeek or direct editor)**: Two modes supported:
   - **DeepSeek mode**: Calls DeepSeek API to generate a three-part title (<=25 chars, two commas splitting three segments) + >600-word article based on the fetched post text. Prompt enforces: diverse openings (7 techniques), no AI flavor, no mechanical connectors, colloquial tone, neutral stance. Title is validated for three-part structure and retried if non-compliant.
   - **Direct editor mode** (when DeepSeek API is unavailable or balance insufficient): The assistant directly authors the article based on the fetched Weibo post text, following the same standards (three-part title, >600 words, diverse opening, no AI flavor, no erhua).
4. **Human-editor polish**: A second LLM pass (or editor pass) acts as a real human copy editor. Preserves all facts and core viewpoints, deletes empty pleasantries / mechanical connectors / flowery parallelism / repetitive conclusions / textbook-style endings, adjusts sentence rhythm, restores natural human writing feel. No meme-stacking, no forced slang, no fabricated stories.
5. **Image fetch & processing**: Prioritizes Weibo original post images (via `/ajax/statuses/search` API, extracts `pic_infos` large/largest/original URLs), falls back to Baidu Images if insufficient. Applies Pillow processing (preserve original aspect ratio — no cropping, contrast/sharpness/color enhancement, unsharp mask, max width 1200px, JPEG quality 92). 5 images per article. Filters low-res images (width<500 or height<300).
6. **Pre-upload self-check & regenerate loop (MANDATORY, per-article)**: **Before any article is saved or uploaded to the draft box, a full self-check MUST run.** The check has three priority dimensions: (A) Opening quality, (B) Human-editor polish quality, (C) Image compliance. If ANY dimension fails, the article is NOT uploaded — the specific failing step is re-run (regenerate opening / re-polish / refetch & re-layout images), the self-check runs again, and the loop repeats until all three dimensions pass. Max 3 regenerate attempts; if still failing after 3 attempts, the article is logged as rejected and the batch proceeds to the next one. See the full checklist in the "Pre-Upload Self-Check" section below.
7. **HTML output**: Embeds images as base64 into a styled HTML file. Saves to `./output/hot_<category>_<index>_<timestamp>.html`. Cover images saved separately to `./output/covers/`.

## Usage

### Single article

```bash
python hot_news_writer.py 娱乐   # Entertainment
python hot_news_writer.py 体育   # Sports
python hot_news_writer.py 社会   # Society
```

### Preview category hot searches (no generation)

```bash
python _preview.py      # 9 topics (3 per category)
python _preview6.py     # 6 topics (2 per category)
```

Lists topics, skipping previously used ones. User confirms before generation.

### Fetch Weibo original post text (source material)

```bash
python fetch_weibo_posts.py
```

Fetches up to 8 original posts per topic from `_preview_result.json`, saves to `_weibo_posts_raw.json`. Article content is based on this real post text, not fabricated.

### Batch generate articles

```bash
python batch_generate.py    # 9 articles via DeepSeek API (needs config.json)
python generate_9.py         # Editor-authored articles, NO DeepSeek needed, NO config.json needed
python generate_single.py    # Single editor-authored article
```

`generate_9.py` reads editor-authored articles from `_manual_articles.json` (list format, recommended — self-contained with category/keyword) or `articles_9.json` (dict format, needs `_preview_result.json` for category). Does NOT call `load_config()` — uses sensible defaults (`output_dir=./output`, `image_count=5`). Applies `clean_erhua()` + three-part-title/word-count validation, saves covers via `save_cover_images()`.

Each article goes through: post text fetch (optional) -> authoring (DeepSeek or editor) -> human-editor polish -> image fetch -> HTML + cover save. Results saved to `./output/batch_manifest.json`.

### Batch upload to Toutiao drafts

```bash
python batch_upload.py          # Upload all articles in manifest
python batch_upload.py 4        # Resume from 4th article (breakpoint recovery)
```

Reads `batch_manifest.json`, uploads each article via `upload_visible.py` to the Toutiao creator platform draft box. Cover upload is enabled by default (SKIP_COVER=0). Supports breakpoint resume via command-line start index.

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
- Article content must be based on fetched Weibo original post text, not fabricated;
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

- 5 images per article. Sourcing strategy (topic-aware, in priority order):
  1. **Weibo topic original posts** — search via `/ajax/statuses/search?q=#{keyword}#` (use the `word_scheme` topic tag like `#哪吒159亿票房为何换不来全体起立#`, NOT the raw `word`). This ensures we only fetch images from posts inside the trending topic itself, avoiding irrelevant bloggers' content. Extract `pic_infos` original/largest/large URLs.
  2. **Baidu Images fallback** — when the topic search returns fewer than `count` images (common for discussion-only topics where users post text-only opinions; e.g. a topic with 50 posts may have only 1 with an image). Baidu does real image-content search and will surface related posters/stills/etc.
- Filter low-res images: skip images <8KB or width<500 or height<300 (ensures people in images are clearly visible);
- Preserve original aspect ratio — no cropping (keeps full image content);
- Filters (contrast +12%, sharpness +30%, color +8%, unsharp mask 90%);
- Max width 1200px (downscale only, never upscale), JPEG quality 92, base64-encoded;
- 3 cover images saved separately as JPEG files to `./output/covers/` — **uploaded by default** (SKIP_COVER=0);
- Dynamic layout (5 images cap): 1 image after paragraph 1, then fill 2-image groups "every 2 paragraphs" forward; when the last group leaves >2 pure-text paragraphs at the tail, shift the last 2-image group back to leave exactly 2 paragraphs at the end — ensures no 3–4 paragraph long text tail.

## Category Hot Search API

Weibo provides official category hot search endpoints (no login required, accessible via visitor session):

| Category | API Endpoint |
|----------|-------------|
| 娱乐 (Entertainment) | `https://weibo.com/ajax/statuses/entertainment` |
| 体育 (Sports) | `https://weibo.com/ajax/statuses/sport` |
| 社会 (Society) | `https://weibo.com/ajax/statuses/social` |

Each returns `data.band_list` with ~50 items. `_parse_band_list()` normalizes them (skips ads, extracts word/rank/num/category). Cross-category deduplication via `used_titles` set ensures no duplicate topics across categories.

## Weibo Original Post Text Fetch

`fetch_weibo_posts.py` fetches original post text as source material for article authoring:

1. Reads `_preview_result.json` for confirmed topics.
2. Calls `/ajax/statuses/search` API for each topic keyword.
3. Extracts up to 8 posts per topic: user, text, created_at.
4. Saves to `_weibo_posts_raw.json`.
5. Article content is authored based on this real post text, ensuring no fabrication.

`fetch_weibo_posts_text()` in `hot_news_writer.py` is the core function. It handles Weibo search API pagination and text extraction from `text_raw` or `text` fields.

## Pre-Upload Self-Check & Regenerate Loop (MANDATORY, runs per-article BEFORE save)

**This is a hard gate.** No article may be saved to the draft box (whether via browser automation or direct API) until all three dimensions below pass. If a dimension fails, the corresponding step is regenerated and the full self-check runs again — up to 3 attempts per article. If still failing after 3 attempts, the article is skipped and logged with failure reasons (does NOT block remaining articles in a batch).

### Dimension A — Opening Quality (highest priority, checked first)

Run these checks against the **first three sentences** of the article (the opening):

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| A1 | **No banned patterns** | Opening does NOT contain: 刷到/看到/点开+热搜/榜单/话题；朋友圈里/群里/评论区；热搜第X位；近日/近日来；话说回来/闲来无事 | Regenerate opening, switching to a different opening technique from the 7 below |
| A2 | **Uses one of 7 techniques** | The opening clearly matches one of: 场景切入 / 细节切入 / 提问切入 / 观点切入 / 对比切入 / 故事切入 / 情感切入 | Regenerate opening with explicit technique assignment |
| A3 | **Grabs attention within 3 sentences** | No roundabout padding; the first 3 sentences contain a concrete scene, detail, question, opinion, contrast, story beat, or emotion hook | Rewrite opening to be tighter, drop filler sentences |
| A4 | **Technique diversity** | Across a batch (3+ articles), no two adjacent articles use the same opening technique | Shuffle technique assignment for the failing article |
| A5 | **No AI flavor in opening** | No 首先/其次/最后/不难看出/值得一提的是；no parallel-clause stacking (是…也是…更是…)；no empty adjectives (令人深思) | Re-polish opening only |
| A6 | **No erhua** | No 事儿/点儿/地儿/哥们儿/玩意儿 in the opening (run `clean_erhua()` and re-check) | Apply `clean_erhua()` + manual review |

### Dimension B — Human-Editor Polish Quality (checked second)

Verify the **full article body** (after the polish step) against these rules:

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| B1 | **Mechanical connectors removed** | Zero occurrences of: 首先 / 其次 / 最后 / 总之 / 综上所述 / 不难看出 / 值得一提的是 | Re-run `polish_article()` with explicit focus on deleting connectors |
| B2 | **No flowery parallelism** | No 是…也是…更是… / 不仅…而且…还… clause stacking anywhere | Re-polish: break stacks into separate short sentences |
| B3 | **No empty adjective stacking** | No 令人深思、发人深省、意义深远 type clusters | Re-polish: delete or replace with concrete observation |
| B4 | **No repetitive / textbook endings** | Last paragraph is NOT a summary ("总的来说… / 综上所述…") but a comment-prompting hook (e.g., a question, a personal take, or an open reflection) | Rewrite last 1-2 paragraphs |
| B5 | **Word count preserved** | Polished article >600 words (same hard requirement as initial draft); if polish reduced below 600, supplement content | Expand a middle paragraph with extra background or context, then re-polish |
| B6 | **Facts & viewpoints unchanged** | All original factual claims and core viewpoints from step 3 are still present in the polished text; nothing was fabricated during polish | Diff the two versions, restore any accidentally deleted factual content |
| B7 | **No meme-stacking / forced slang** | No piled-up internet slang; language is colloquial but natural, like chatting with a friend | Re-polish to natural tone |
| B8 | **Natural sentence rhythm** | Mix of long and short sentences; no run-on paragraphs (>150 chars per paragraph on average) | Re-polish sentence breaks |
| B9 | **Erhua clean** | Full article has no 儿化音 residue (run `clean_erhua()` final pass; verify against `_ERHUA_MAP` 24 groups + regex fallback) | Run `clean_erhua()` + manual sweep |

### Dimension C — Image Compliance (checked third)

Verify the **5 body images + 3 cover images + layout + captions**:

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| C1 | **Exactly 5 body images** (or 3 if `image_count=3` explicitly set) | Count matches the configured `image_count` (default 5); not 4, not 6 | If short: continue image pipeline to next source layer; if excess: remove last group and re-layout |
| C2 | **Image resolution** | All 5 images pass: file size ≥8KB, width ≥500px, height ≥300px. People (if any) are clearly visible | Reject low-res images and fetch replacements from next pipeline layer |
| C3 | **Aspect ratio preserved** | No cropping. Pillow processing keeps original ratio (max-width 1200px downscale only, never upscale) | Re-run Pillow processing without crop step |
| C4 | **Image-relevance check** | Each image visually matches the article topic (not a generic placeholder). If Baidu fallback was used heavily, verify keyword accuracy | Refine search keywords and refetch; if 2+ images are off-topic, refetch the whole set |
| C5 | **Dynamic layout correct** | Using `calc_image_layout(total_paragraphs, 5)` rules: (a) 1 image after paragraph 1; (b) remaining 2-image groups placed with max pure-text gap ≤3 paragraphs between adjacent groups; (c) tail pure-text = 2 or 3 paragraphs; (d) no image touches the article end (tail ≥1) | Re-run layout algorithm and verify against the 4 rules |
| C6 | **Captions present & centered** | Every body image has a `<p style="text-align:center;font-size:12px;color:#999;">图片来源于网络</p>` caption **immediately below** the `<img>` tag. Zero images are missing captions | Insert captions for any image lacking one; verify HTML/DOM order |
| C7 | **Cover images: exactly 3** | `./output/covers/` has 3 distinct JPEG cover files per article; all are ≥8KB & ≥500×300 | Regenerate covers from the best 3 of the 5 body images, or refetch extras |
| C8 | **No stale temp files** | Before upload, `output/tmp/body_img_*` must be cleaned so the current article's images are used (not leftover from a previous article) | Delete all `body_img_*` from tmp dir before extraction |
| C9 | **Source diversity recorded** | Manifest `image_source` field reports actual layer composition (e.g. `微博(4张) + 百度(1张)`); not left blank or generic | Re-run fetch with source-tracking enabled |

### Regenerate Loop Logic (pseudo-code)

```
for each article in manifest order:
  attempts = 0
  while attempts < 3:
    checks = run_self_check_A_B_C(article)
    if checks.all_pass:
      proceed_to_upload(article)
      break
    else:
      attempts += 1
      if checks.fail_A:
        article = regenerate_opening(article, checks.fail_A_details, force_new_technique=True)
      if checks.fail_B:
        article = re_polish_article(article, checks.fail_B_details)
      if checks.fail_C:
        article = refetch_relayout_images(article, checks.fail_C_details)
      # Re-check includes regenerated parts — full A+B+C every iteration
  else:
    log_to_batch_result("SKIPPED (3 attempts failed)", article.title, checks.failure_summary)
    continue to next article
```

---

## Toutiao Draft Upload

The skill includes `upload_visible.py` for uploading generated articles to the Toutiao creator platform draft box. It uses DrissionPage to drive a real Chrome browser (non-headless).

### Upload Flow

0. **Pre-upload self-check (MANDATORY — runs BEFORE opening the publish page)**: Execute the full A+B+C self-check above for this specific article. If any dimension fails, enter the regenerate loop. **Do NOT open the browser or call save API until self-check passes.**
1. **Login**: Load cookies from `toutiao_cookies.json` and navigate to `mp.toutiao.com`.
2. **Create new article**: Open the publish page, wait for the ProseMirror editor to mount.
3. **Fill title**: Use native `value setter` + `input`/`change` events to trigger React state update (DrissionPage's `input()` doesn't work for React-controlled title textarea).
4. **Upload body images**: Two-stage approach:
   - Stage 1: Upload all images one-by-one by pasting Blob via `ClipboardEvent('paste')`, capturing returned server URLs.
   - Stage 2: Set all content (text + images) at once via ProseMirror `view.dispatch()` API with properly structured image nodes.
5. **Upload covers**: By default `SKIP_COVER=0` uploads 3 covers via file input. Set `SKIP_COVER=1` to skip.
6. **Pre-save re-check (lightweight, in-page)**: Before clicking Save / calling the publish API, do a quick DOM check: (a) title has 2 commas / 3 segments; (b) 5 images present in DOM; (c) each `<img>` is immediately followed by a caption `<p>` node. If any mismatch, fix in-page before saving.
7. **Save / auto-save to draft box**: Trigger save (or let auto-save commit). The save request must include: `save='1'`, `draft_form_data={"coverType":3}`, `pgc_feed_covers=[3 cover URLs]`.
8. **Verify**: Check draft list for the article; confirm the saved article's title matches and images are present.

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

`batch_upload.py` reads `batch_manifest.json` and uploads each article sequentially. **For every single article in the manifest, the pre-upload A+B+C self-check runs BEFORE the upload subprocess is spawned.** If an article fails self-check after 3 regenerate attempts, it is skipped (logged) and the batch moves to the next article — the batch never stalls on one failing article.

Supports a command-line start index for resuming after interruptions:

```bash
python batch_upload.py 4   # Resume from 4th article (self-check still runs for 4th+)
```

Each article upload runs as a subprocess with a 180s timeout. Logs are written to `batch_upload.log` with timestamps, including self-check pass/fail per article and (if applicable) which dimension failed and what regeneration step was run.

## Dependencies

- Python 3.10+
- `requests`, `Pillow`, `DrissionPage`
- DeepSeek API key (in config.json) — **optional**, falls back to direct editor mode when unavailable
- Toutiao cookies (in toutiao_cookies.json, for upload only)
- Network access to: weibo.com, api.deepseek.com (optional), image.baidu.com, mp.toutiao.com

## Error Handling

- If Weibo visitor system fails to get SUB cookie: raises RuntimeError.
- If Weibo original post images are insufficient: falls back to Baidu Images.
- If DeepSeek API fails (402 = insufficient balance, missing key): falls back to direct editor authoring mode.
- If title fails three-part validation: automatically retries once.
- **Pre-upload self-check failure loop**: If an article fails opening / polish / image compliance check after 3 regenerate attempts, it is skipped (logged) and the batch proceeds — one bad article never blocks the rest.
- If batch upload stalls: use `python batch_upload.py <start_index>` to resume (self-check still runs for resumed articles).
- If cover upload fails: article content is still saved; covers can be manually added later. Set `SKIP_COVER=1` to skip cover upload entirely.
- **Stale temp images**: `upload_visible.py` saves body images to `output/tmp/body_img_N.jpg` before uploading. If these files persist from a previous article, they will be reused by mistake, causing the wrong images to appear in the new article. Fixed: all `body_img_*` files are cleared before each upload, forcing fresh extraction from the current article's base64 data.
- **Baidu image encrypted objURL**: Some Baidu image results return encrypted `objURL` that cannot be directly downloaded. Fixed: prioritize `middleURL`/`thumbURL` (always accessible) over `objURL`.
