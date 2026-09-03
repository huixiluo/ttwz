---
name: "toutiao-hotspot-writer"
description: "Fetches Toutiao hot-board topics, classifies into entertainment/sports via keyword rules, fetches Toutiao article/comment text as source material, rewrites them into 650-750-char articles with three-part click-worthy titles (20-30 chars) via DeepSeek or direct editor authoring, polishes with a human-editor pass, generates 10 candidate titles per finalized article for manual selection, fetches images via a 5-layer pipeline (original article body images via DrissionPage -> Toutiao hot-board thumbnail -> Toutiao topic page body images -> Weibo topic post images -> Baidu Images fallback), and outputs HTML files. Supports batch generation and Toutiao draft upload."
---

# Toutiao Hotspot Writer

This skill fetches Toutiao hot-board topics, classifies them into 娱乐/体育 two categories via keyword rules (时政社会/society topics are NOT fetched per user mandate, 2026-09-03), fetches Toutiao topic article/comment text as source material, rewrites them into polished articles (650-750 chars) with three-part titles, applies a human-editor polish pass, fetches images via a 5-layer priority pipeline (original article body images via DrissionPage -> Toutiao hot-board thumbnail -> Toutiao topic page images -> Weibo topic post images -> Baidu Images fallback), and outputs standalone HTML files. Supports batch generation and Toutiao draft upload.

## When to Invoke

**This is the DEFAULT skill for article generation.** When the user does not explicitly specify a platform (e.g. just says "生成文章", "批量生成上传草稿箱", "写几篇资讯"), this skill runs by default.

- User asks to generate rewritten articles from Toutiao hot trends
- User wants to produce entertainment/sports news content from current trends **without specifying a platform** (defaults to Toutiao hot-board; society/时政社会 topics are excluded)
- User asks to batch-generate multiple articles and upload to Toutiao drafts
- User explicitly mentions "头条" / "Toutiao"

## How It Works

The core pipeline has 9 steps:

1. **Fetch news topics (czgts first, Toutiao hot-board fallback)**: The **primary source** is the 创作罐头 low-fans-viral board (`https://www.czgts.cn/v1/hots/popular`, "热门素材 → 低粉爆款"), fetched via `czgts_source.fetch_czgts_low_fans()`. Fixed filters: platform=今日头条, content type=文章, fans<10k (`fansLimits="0_10000"`), publish time within 1 day (24h window, `startTime`/`endTime` as `"YYYY-MM-DD HH:MM:SS"` strings — timestamps in ms/s are rejected with code 997 or match 0 rows; default `within_hours=24`, `None`/`0` disables), sorted by read/play count descending (`sortBy=1`, `postType=3`), categories 娱乐/体育 only (the czgts "时政社会" domain is NOT fetched — user mandate 2026-09-03; society topics are excluded entirely, no political-keyword filtering needed anymore). Underlying API `POST /muse/content/api/v1/hots/search` is called with plain `requests` (no login, no cookies needed — verified by live test; the old DrissionPage-in-browser fetch was retired along with its lxml cp311 dependency). Each article's `keywords` (top-2 joined) become the search word. Falls back to the Toutiao PC hot-board API (`https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc`, ~50 topics, keyword-classified, only 娱乐/体育 picked) when czgts fails or returns no usable topics.
2. **List & confirm topics (MANDATORY pause)**: After fetching, the skill **must** list all candidate topics with their title, rank, heat value, and assigned category, then **stop and wait for user confirmation** before proceeding. The skill must NOT automatically start article generation. The user may approve the list as-is, remove specific topics, swap topics, or adjust category assignments. Only after the user explicitly confirms does the skill proceed to step 3. This is a hard gate — no downstream step (text fetch, authoring, images, HTML) may run before confirmation.
3. **Fetch Toutiao topic article/comment text**: For each confirmed topic, scrapes the Toutiao trending topic page (or related article URLs) to fetch up to 8 article snippets / hot comments as source material for article rewriting. Saved to `_toutiao_posts_raw.json`. This ensures article content is based on real Toutiao discussions, not fabricated.
4. **Article authoring (DeepSeek or direct editor)**: Two modes supported:
   - **DeepSeek mode**: Calls DeepSeek API to generate a three-part title (20-30 chars, two commas splitting three segments, packing 事件+人物+悬念) + 650-750-char article based on the fetched post text. Prompt enforces: diverse openings (7 techniques), no AI flavor, no mechanical/transition connectors (including 然而/但是), colloquial tone, neutral stance. Title is validated for three-part structure and retried if non-compliant.
   - **Direct editor mode** (when DeepSeek API is unavailable or balance insufficient): The assistant directly authors the article based on the fetched Toutiao topic text, following the same standards (three-part title, 650-750 chars, diverse opening, no AI flavor, no erhua).
5. **Human-editor polish**: A second LLM pass (or editor pass) acts as a real human copy editor. Preserves all facts and core viewpoints, deletes empty pleasantries / mechanical connectors / transition words (然而/同时/总而言之 etc.) / flowery parallelism / repetitive conclusions / textbook-style endings, adjusts sentence rhythm, restores natural human writing feel. Every paragraph enters the topic directly; the ending states the view directly with zero summary/transition words. No meme-stacking, no forced slang, no fabricated stories.
6. **Image fetch & processing**: Uses a 5-layer priority pipeline via `fetch_images_unified()`: (0) original article body images — `fetch_images_from_article_page()` opens the czgts topic's original Toutiao article URL in the already-open DrissionPage browser (bypassing the JS challenge that returns an empty shell to plain requests), extracts content-scope `<img>` URLs (natural size >=500x300, or lazy `data-src`), filters logo/avatar/icon/qrcode/sprite URLs, then downloads via requests; enabled only when the caller passes `page` (the batch draft-upload pipeline does); (1) Toutiao hot-board thumbnail (from the API `Image` field, normalized by `_extract_image_url()` to handle dict/str formats); (2) Toutiao topic detail page body images (regex-extracted from `toutiaoimg.com` URLs); (3) Weibo topic post images (visitor-session + `#keyword#` search via `/ajax/statuses/search`, extracts `pic_infos` original/largest/large URLs); (4) Baidu Images fallback. Each layer fills only the remaining count needed; final source composition is reported (e.g. `原文(3张) + 微博(2张)`). All layers go through the SAME processing rules: Pillow processing (preserve original aspect ratio — no cropping, contrast/sharpness/color enhancement, unsharp mask, max width 1200px, JPEG quality 92) and dHash dedup — original-article images are never used raw. 5 images per article. Filters low-res images (width<500 or height<300).
7. **Pre-upload self-check & regenerate loop (MANDATORY, per-article)**: **Before any article is saved or uploaded to the draft box, a full self-check MUST run.** The check has three priority dimensions: (A) Opening quality, (B) Human-editor polish quality, (C) Image compliance. If ANY dimension fails, the article is NOT uploaded — the specific failing step is re-run (regenerate opening / re-polish / refetch & re-layout images), the self-check runs again, and the loop repeats until all three dimensions pass. Max 3 regenerate attempts; if still failing after 3 attempts, the article is logged as rejected and the batch proceeds to the next one. See the full checklist in the "Pre-Upload Self-Check" section below.
8. **HTML output**: Embeds images as base64 into a styled HTML file. Saves to `./output/tt_hot_<category>_<index>_<timestamp>.html`. Cover images saved separately to `./output/covers/`.
9. **Title candidates & manual selection (MANDATORY pause, batch-level)**: After ALL articles in the batch are finalized (polished), generate **10 candidate titles per article based on the final article content** — eye-catching, click-attracting, "标题党"-style three-part titles (20-30 chars incl. punctuation, each packing 事件+人物+悬念), creative/novel/attractive while accurately reflecting the article's key highlights. Candidates come from `title_candidates.py` (LLM mode via `generate_title_candidates()`, or editor mode via `_manual_title_candidates.json`); the script auto-detects the newest manifest (`batch_manifest.json` or `batch_manifest_tt.json`). All candidates for every article are listed together (numbered, with the current title as option 0), and the skill **STOPS and waits for the user to pick one title per article**. Selections are applied via `python title_candidates.py apply 1:3 2:1 3:0` (0 = keep current title), which updates the manifest titles and patches HTML `<title>`/`<h1>`. **No upload runs before the user confirms title selections.**

## Usage

### Single article

```bash
python toutiao_hot_writer.py 娱乐   # Entertainment
python toutiao_hot_writer.py 体育   # Sports
```

(Society/社会 single-article mode is retired — 时政社会 topics are not fetched per user mandate.)

### Preview & confirm hot-board topics (MANDATORY before any generation)

```bash
python _preview_tt.py      # 6 topics (3 per category, 娱乐+体育)
python _preview6_tt.py     # 4 topics (2 per category, 娱乐+体育)
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

### Staged pipeline with hard gates (batch_n_tt_pipeline.py — preferred for full rounds)

The end-to-end pipeline `batch_n_tt_pipeline.py` is **stage-based with TWO mandatory human-confirmation gates** (mirrors the 9-step flow; the old auto-run-through mode was removed because it skipped both gates and used a template author):

```bash
python batch_n_tt_pipeline.py topics [K]      # [1] fetch czgts topics (1-day window), list K=3 candidates PER CATEGORY (9 total), STOP
python batch_n_tt_pipeline.py confirm 1,4,7   # gate 1: record user's topic picks by index, one per category typically (or "all")
python batch_n_tt_pipeline.py material        # [2] open each original article page in Edge, extract real body text -> _pipeline_material.md (thin material <500 chars only prints a warning; NO auto-swap — user's confirmed topic selection is final)
python batch_n_tt_pipeline.py generate        # [4] validate _pipeline_articles.json (assistant-authored from the material) via code-level self-check; then images (original-page quota 3 + weibo fill + baidu fallback), HTML, covers, manifest
python title_candidates.py                    # gate 2: 10 candidates per article, STOP for user picks (editor mode via _manual_title_candidates.json)
python title_candidates.py apply 1:3 2:1 3:0  # apply picks
python batch_n_tt_pipeline.py upload          # [6] upload with server-response verification (XHR capture of article/publish, code==0) + draft_list API recheck
```

Key rules enforced in code:
- `topics` lists **3 candidates per category** (6 total: 娱乐 + 体育). The czgts "时政社会" domain is NOT fetched at all (user mandate 2026-09-03) — no society candidates, and the old political-keyword pre-filter (POLITICAL_KEYWORDS/is_political) has been removed as dead code.
- `material`/`generate`/`upload` refuse to run before `confirm` (state file `_pipeline_state.json` tracks the stage); `upload` refuses if `output/title_candidates.json` is missing (title gate).
- `generate` self-check: three-part title (two commas, 20-30 chars, each segment <=10, packing 事件+人物+悬念), 650-750 chars (whitespace-stripped), 6-8 paragraphs, each paragraph <=150 chars, banned openings (刷到/看到/点开+热搜, 近日, single-sentence first paragraph), banned connectors (首先/其次/最后/总之/然而/但是/同时...), banned parallel stacking, banned ending templates (评论区聊聊 etc.), erhua-clean, adjacent articles must not share opening/ending. Any failure → detailed report + exit 1, NO manifest, NO upload.
- Articles are authored by the assistant (editor mode) from the REAL extracted material (`_pipeline_material.md`), not from templates. Format: `_pipeline_articles.json` = `[{"category", "keyword", "title", "article"}]`, keyword must match the confirmed topic's word.
- Save verification is honest: the in-page toast lies under headless/risk-control (7050 保存失败 still shows "草稿保存中"), so `upload_to_draft` captures the `article/publish` XHR response and requires `code==0`, then re-verifies every article via the draft_list API after the browser closes. Windows local runs use visible Edge (headless Chrome is rejected by Toutiao risk control on write APIs).

### Generate 10 candidate titles & manual selection (MANDATORY before upload)

```bash
python title_candidates.py                  # Generate 10 candidates per article, list all, STOP for user selection
python title_candidates.py apply 1:3 2:1 3:0  # Apply user picks (0 = keep current title); updates manifest + HTML titles
```

After all articles are finalized, `title_candidates.py` generates 10 candidate titles per article based on the final article content. It auto-detects the newest manifest (`output/batch_manifest.json` or `output/batch_manifest_tt.json`). Candidate sources (auto-detected): editor mode uses `_manual_title_candidates.json` (assistant-authored, format `[{"keyword": "...", "candidates": [...]}]`); otherwise LLM mode calls `generate_title_candidates()` from `toutiao_hot_writer.py`/`hot_news_writer.py` (needs `config.json`). Candidates are validated (three-part, 20-30 chars, packing 事件+人物+悬念, erhua-cleaned) and saved to `./output/title_candidates.json`.

The skill lists all candidates (current title = option 0) and **pauses for the user to pick one per article**. Apply picks via the `apply` subcommand — it updates the manifest titles and patches `<title>`/`<h1>` in the HTML files. **Upload only runs after selection is applied.**

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

### Title - Three-part structure (20-30 chars, strictly enforced)

**标题规则速查（中文）**：
- **两种结构**：A（事件+细节+悬念）：适合有戏剧性细节的话题；B（现象+冲突+提问）：适合有争议/反差的话题
- **节奏**：每段≤10字，干脆、口语化
- **吸引力**：制造悬念/冲突/反差，可用数字、对比、情绪词，但不做欺骗性标题党
- **真实中立**：标题与内容匹配，不捏造；不站队、不点名攻击

1. **Must be three-part**: title consists of three short phrases separated by Chinese commas. Exactly two commas, three segments. Example: "明星哭穷上热搜，网友不买账，这届观众清醒了". Single-segment or two-segment titles are rejected.
2. 20-30 chars (including punctuation), no less than 20 chars — semantically complete, no half-sentences. **Each title must pack all three elements: 事件 (what happened), 人物 (who is involved), 悬念 (why click)**. Thin titles that only carry one or two elements are rejected even if formally valid — fill the elements to make the title substantial;
3. Choose from two structures based on the topic content:
   - **Structure A (event + detail + suspense)**: state the event, add a key detail, end with suspense. Preferred when the topic has dramatic details.
   - **Structure B (phenomenon + conflict + question)**: describe the phenomenon, point out the conflict, end with a question. Preferred when the topic involves controversy or contrast.
4. Each segment <=10 chars, punchy rhythm, colloquial, no written-style tone;
5. Create suspense/conflict/contrast; may use questions, numbers, contrast, emotional words. No clickbait scam;
6. No low-quality clickbait words;
7. Title must match content; no fabricating unverified facts;
8. Neutral and objective. No favoring or naming specific persons;
9. **Self-check**: after writing, verify the title has exactly two commas, three segments, 20-30 chars, and carries all three elements (事件+人物+悬念). If not, rewrite.
10. **Code-level validation**: `_is_three_part_title()` checks comma count == 2; non-compliant titles trigger one retry. Over-length titles (>30 chars) are smart-truncated in `_parse_llm_output()`.
11. **Erhua post-processing**: `clean_erhua()` function removes any erhua suffixes from both title and article (24 replacement groups + regex fallback, excluding valid 儿 words like 儿女/儿童/儿子).

### Viral title candidates (10 per article, manual selection - strictly enforced)

After the final article content is fixed (post-polish), generate **10 candidate titles based on the final article content** via `title_candidates.py`:

1. Eye-catching, click-attracting, "标题党"-style three-part titles, 20-30 chars each (including punctuation) — no less than 20 chars; each title must pack all three elements: 事件 (what happened), 人物 (who is involved), 悬念 (why click). Thin titles that only carry one or two elements are rejected even if formally valid;
2. Must attract reader interest AND accurately reflect the article's key highlights — no fabrication, no distortion;
3. Emphasize creativity, novelty, and attractiveness; the 10 candidates must differ clearly in angle, sentence pattern, and cut-in point (no homogenization);
4. Each candidate must pass the same hard validation: exactly two commas / three segments, 20-30 chars, erhua-cleaned;
5. All candidates are listed together and the skill **pauses for the user to manually pick one per article**. **Display format (fixed, user-mandated)**: per article show a table with the current title as option 0 ("保持原标题：..."), then every candidate as a numbered row with its character count appended (e.g. "标题文本（26字）"), so the user sees 原标题 + 候选标题 + 序号 + 字数 at a glance. The user may pick by index (e.g. `1:6 2:1 3:2`) or supply a custom title text for an article — custom titles are validated with the same rules (three-part, 20-30 chars, three elements) before being applied;
6. The selected title is applied via `python title_candidates.py apply 1:3 2:1 3:0` (0 = keep current) — updates the manifest (`batch_manifest.json` / `batch_manifest_tt.json`) and HTML `<title>`/`<h1>`. Upload runs only after selection.

### Article (650-750 chars, strictly enforced)

- **650-750 chars (whitespace-stripped, hard-enforced by the generate self-check — articles below 650 or above 750 are rejected)**, 6-8 paragraphs (hard-enforced), each <=150 chars (hard-enforced; >600 remains the absolute platform minimum);
- Article content must be based on fetched Toutiao topic article/comment text, not fabricated;
- Positive tone, reader-resonant; the ending leaves an aftertaste through content itself, NOT through templated interaction-bait (see "Ending - Diverse" section below);
- Neutral and objective, no favoring or attacking specific persons;
- Supplement background info or extended content to add depth.

### Toutiao platform compliance (首发激励计划 rules, enforced in pipeline P-checks)

Per Toutiao's "首发激励计划" (baike 242/566), articles flagged as 套路模板化/低成本创作 get the 首发 function frozen (14 days first, permanent after 2 strikes), and 洗稿/搬运 content is ruled 非原创 (no revenue share). The pipeline's generate stage enforces these as **P-checks**:

1. **Titles — no exaggerated suspense clickbait (P-标题)**: banned words include 真相来了/你怎么看/你怎么想/怎么回事/看完惊呆/网友炸锅/全网沸腾/惊人一幕/细思极恐/大揭秘/内幕曝光 etc. The platform explicitly names "夸张悬念式标题" as 套路模板化发文. Within one batch, two titles must NOT share an identical segment (P-批标题, fixed-format posting);
2. **Originality — rewrite, don't paraphrase-copy (P-原创)**: the article's 10-char continuous overlap ratio with the source material must stay <=25%. Writing means restructuring with your own analysis and phrasing; verbatim runs of the source longer than ~10 chars are treated as 大篇幅引用 (non-original). Quotes of official statements are fine in moderation;
3. **No info-dump paragraphs (P-罗列)**: paragraphs that merely enumerate >=4 items with 顿号 and no complete sentences are flagged as low-cost 信息罗列;
4. **Viewpoint required**: pure event re-narration without the author's own analysis/opinion is 内容空洞水化 — every article must contain original viewpoint or analysis paragraphs (this is a writing-discipline rule, checked by the editor, not code);
5. **Facts only from material**: 捏造细节/编虚假故事 is a platform violation — all factual details (names, dates, numbers, quotes) come from the fetched material only;
6. **Timeliness**: the czgts topic source is already filtered to articles published within 1 day (satisfies 首发时效); write and publish the same day.

### Opening - Diverse & natural (strictly enforced)

**Banned opening patterns**:
- "刷到/看到/点开 + 热搜/榜单/话题" patterns;
- "朋友圈里/群里/评论区" patterns;
- Self-referencing rank ("热搜第X位");
- "近日/近日来/近日，一则..." news-template patterns;
- "话说回来/闲来无事" filler;
- **Single-sentence-paragraph openings**: the first paragraph must NOT be just one lone hook/suspense/exclamation sentence standing alone (a recent固化 pattern). The first paragraph must be a natural paragraph of 2+ sentences: hook sentence first, immediately followed by 1-3 expansion sentences (background, who/when, event push) so the hook is woven into the narrative flow. Do not frequently use single-sentence paragraphs elsewhere either.

**7 opening techniques** (choose the most fitting one per article, avoid repeating):
- Scene cut-in: a concrete life scene or image;
- Detail cut-in: start from the most gripping detail/quote/action;
- Question cut-in: a thought-provoking question;
- Opinion cut-in: lead with a judgment or stance;
- Contrast cut-in: past-vs-present or appearance-vs-reality;
- Story cut-in: natural storytelling opening;
- Emotion cut-in: directly state a feeling for empathy.

Must grab the reader within the first three sentences. No roundabout padding.

### Ending - Diverse & restrained (strictly enforced)

**Banned ending patterns** (a recent固化 pattern — all articles ended with "question + 评论区聊聊", which is strictly forbidden now):
- "提问+评论区" template: "你怎么看？评论区聊聊" / "评论区说说你的看法" / "评论区聊" — ANY question followed by a 评论区 call-to-action is banned;
- Template interaction-bait tails: "欢迎留言讨论" / "大家怎么看呢" / "说说你的观点" and similar universal tails;
- Empty summary-elevation endings: "这不仅xxx，更是xxx的体现" / "时间会给出答案".

**7 ending techniques** (choose the most fitting one per article; adjacent articles in a batch must NOT use the same technique):
- 画面留白式 (scene-blank ending): close on a concrete scene/detail/action and stop — the aftertaste lives in the image;
- 观点直陈式 (verdict ending): one clean sentence stating the stance, no explanation, no padding;
- 数字回扣式 (number-callback ending): end with a key number from the article and let it speak;
- 时间展望式 (forward-look ending): one step into the future — a little suspense or expectation, no verdict;
- 金句式 (punchline ending): one condensed, forceful sentence, with a touch of emotion or attitude;
- 细节呼应式 (echo ending): call back to a detail/person/image from the opening, closing the loop;
- 开放提问式 (open-question ending): one specific, restrained question tied to concrete facts in the article — allowed at most ONCE per batch, and never with any 评论区 tail.

Rules:
- The ending must contain zero summary/transition words (same as the style rules);
- The open-question technique is the LAST choice — prefer the other six;
- Editor-mode articles (`_manual_articles_tt.json`) must follow the same rule when authored by the assistant.

### Style (no AI flavor - strictly enforced)

- Ban ALL connecting/transition words: strictly avoid 首先/其次/最后/总之/综上所述/总而言之/不难看出/值得一提的是/同时 AND 然而/但是 plus any other word used to lead or summarize;
- Every paragraph enters the discussion topic directly — no building content through introductory or transitional phrases;
- The final part of the article states the opinion/conclusion directly, avoiding any words/phrases that trigger summarizing or transitioning;
- Ban parallel-clause stacking: 是...也是...更是... / 不仅...而且...还...;
- Ban empty adjective stacking: 令人深思、发人深省、意义深远;
- Ban ending every paragraph with a summary sentence;
- Use diverse sentence structures; inter-paragraph logic flows naturally through content (not through transition words); language matches the target readers' habits and expectations; no stiff jargon stacking or mechanical repetition;
- Write like a sincere conversation with the reader;
- Use colloquial language, like chatting with a friend;
- Vary sentence length. Mix long and short;
- Personal perspective and emotion allowed: 说实话/老实讲/说起来;
- Ban erhua (儿化音): never use 事儿/点儿/地儿/哥们儿/玩意儿. Use standard forms. Enforced both in prompt and via `clean_erhua()` post-processing.
- **Code-level double insurance**: `clean_erhua()` runs after both rewrite and polish — replaces via `_ERHUA_MAP` (long-match first, 24 groups), then regex strips residual `汉字+儿` suffixes (excluding legitimate word-initial 儿 like 儿女/儿童/儿子).

### Human-Editor Polish (second pass)

After the initial draft, `polish_article()` runs a second DeepSeek pass (or editor pass) as a real human copy editor:

- **Preserve**: all original facts, core viewpoints. No tampering, deletion, or fabrication;
- **Delete**: empty pleasantries, mechanical connectors (首先/其次/最后/总之/综上所述/总而言之/不难看出/值得一提的是/同时), transition words (然而/但是 and any other word used to lead or summarize), flowery parallelism, repetitive conclusions, textbook-style endings;
- **Adjust**: sentence length rhythm, diverse sentence structures; inter-paragraph logic connects naturally through content (not transition words); language fits the target readers; no jargon stacking or mechanical repetition — the article should read like a sincere conversation with the reader;
- **Direct entry & direct ending**: every paragraph enters the discussion topic directly (strip introductory/transitional lead-ins); the final part states the opinion/conclusion directly with zero summary/transition words;
- **De-template the ending**: if the draft ends with a "question + 评论区聊聊" template or other universal interaction-bait tail, rewrite it with one of the 7 ending techniques (scene-blank / verdict / number-callback / forward-look / punchline / echo / open-question); adjacent articles in a batch must use different techniques; keep open-question endings at most once per batch, never with a 评论区 tail;
- **Allow**: slight imperfections to restore natural human writing feel;
- **Ban**: meme-stacking, forced slang, fabricated stories/details, template-style writing;
- **Word count**: polished article must remain in the 650-750 char range; if deletion would drop below 650, supplement content to maintain length;
- Keep the original overall tone and paragraph structure. Only polish the prose level.

### Images

- 5 images per article. Sourcing uses a **5-layer priority pipeline** via `fetch_images_unified()` — each layer fills only the remaining count needed, shortfalls fall through to the next layer:
  0. **Original article body images** (layer 0) — enabled when a DrissionPage `page` is passed (the batch draft-upload pipeline passes its upload browser; czgts topics' `url` is the original Toutiao article link). `fetch_images_from_article_page()` navigates the browser to the article URL (requests gets a JS-challenge shell page with 0 images, so a browser context is required), extracts `<img>` URLs scoped to the article content (`article` / `.article-content` / `.syl-article-base` / `.tt-article`, fallback body), keeps natural size >=500x300 or lazy `data-src`/`data-original` URLs, filters URLs containing logo/avatar/icon/qrcode/sprite, then downloads each via requests with Toutiao Referer. Every downloaded image goes through the standard `process_image()` + dHash dedup below — never used raw. Fills remaining slots first, so Weibo/Baidu are only used when the original article has too few usable images.
  1. **Toutiao hot-board thumbnail** (layer 1) — the `Image` field from the hot-board API response. `_extract_image_url()` normalizes the field which may be a dict (`{url, url_list, uri}`) or a string; falls back to `url_list[0]` then `uri`-composed URL. This image is directly tied to the topic.
  2. **Toutiao topic detail page body images** (layer 2) — regex-extracts `toutiaoimg.com` image URLs from the topic page HTML. Fills remaining slots after layer 1.
  3. **Weibo topic post images** (layer 3) — `get_weibo_session()` simulates the Weibo visitor system (SUB cookie, no login), then `fetch_images_from_weibo()` searches `#keyword#` via `/ajax/statuses/search` and extracts `pic_infos` URLs (priority: `original` -> `largest` -> `large`). Weibo topic posts are highly relevant since the same hot topic often trends on both platforms. Layer skipped silently if visitor-session fails.
  4. **Baidu Images fallback** (layer 4) — when all above layers are still short of `count`. Uses real image-content search, prioritizes `middleURL`/`thumbURL` over encrypted `objURL`.
- **Source reporting**: the final composition is returned as a string like `头条(1张) + 微博(3张) + 百度(1张)`, logged and saved to manifest `image_source` field for traceability.
- **Image deduplication (dHash)**: every layer runs `_dedupe_images()` (pure-PIL perceptual hash, no numpy) to remove visually duplicate images; cross-layer, `_is_dup_with()` blocks any image that matches an already-selected one (hamming distance < 15 = same image). Each layer fetches `count*2` candidates so dedup still yields `count` unique images. This prevents the same Weibo photo (original + same-size variant) from appearing twice in one article.
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

Returns a JSON array under `data` with ~50 items. Each item contains: `Rank` (rank), `Title` (title), `HotValue` (heat value), `Url` (topic detail URL), `Image` (thumbnail), `ClusterId` (topic ID), `cluster_type`, etc. `_parse_tt_hot_list()` normalizes them and classifies each item via two-layer strategy (internal classifier still knows 娱乐/体育/社会, but the pipeline's fallback only ever picks 娱乐/体育 — society topics are excluded per user mandate 2026-09-03):

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

## Pre-Upload Self-Check & Regenerate Loop (MANDATORY, runs per-article BEFORE save)

**This is a hard gate.** No article may be saved to the draft box (whether via browser automation or direct API) until all three dimensions below pass. If a dimension fails, the corresponding step is regenerated and the full self-check runs again — up to 3 attempts per article. If still failing after 3 attempts, the article is skipped and logged with failure reasons (does NOT block remaining articles in a batch).

### Dimension A — Opening Quality (highest priority, checked first)

Run these checks against the **first three sentences** of the article (the opening):

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| A1 | **No banned patterns** | Opening does NOT contain: 刷到/看到/点开+热搜/榜单/话题；朋友圈里/群里/评论区；热搜第X位；近日/近日来；话说回来/闲来无事；单句成段式开头（首段仅一句独立成段，首段必须2句以上） | Regenerate opening, switching to a different opening technique from the 7 below |
| A2 | **Uses one of 7 techniques** | The opening clearly matches one of: 场景切入 / 细节切入 / 提问切入 / 观点切入 / 对比切入 / 故事切入 / 情感切入 | Regenerate opening with explicit technique assignment |
| A3 | **Grabs attention within 3 sentences** | No roundabout padding; the first 3 sentences contain a concrete scene, detail, question, opinion, contrast, story beat, or emotion hook | Rewrite opening to be tighter, drop filler sentences |
| A4 | **Technique diversity** | Across a batch (3+ articles), no two adjacent articles use the same opening technique | Shuffle technique assignment for the failing article |
| A5 | **No AI flavor in opening** | No 首先/其次/最后/不难看出/值得一提的是/然而/但是/同时；no parallel-clause stacking (是…也是…更是…)；no empty adjectives (令人深思) | Re-polish opening only |
| A6 | **No erhua** | No 事儿/点儿/地儿/哥们儿/玩意儿 in the opening (run `clean_erhua()` and re-check) | Apply `clean_erhua()` + manual review |

### Dimension B — Human-Editor Polish Quality (checked second)

Verify the **full article body** (after the polish step) against these rules:

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| B1 | **Mechanical connectors & transition words removed** | Zero occurrences of: 首先 / 其次 / 最后 / 总之 / 综上所述 / 总而言之 / 不难看出 / 值得一提的是 / 同时 / 然而 / 但是 (and any other leading/summarizing transition word) | Re-run `polish_article()` with explicit focus on deleting connectors & transitions |
| B2 | **No flowery parallelism** | No 是…也是…更是… / 不仅…而且…还… clause stacking anywhere | Re-polish: break stacks into separate short sentences |
| B3 | **No empty adjective stacking** | No 令人深思、发人深省、意义深远 type clusters | Re-polish: delete or replace with concrete observation |
| B4 | **No repetitive / templated endings** | Last paragraph is NOT a summary ("总的来说… / 综上所述…") AND NOT a "question + 评论区" template or other universal interaction-bait tail; it uses one of the 7 ending techniques (scene-blank / verdict / number-callback / forward-look / punchline / echo / open-question) with zero summary/transition words; adjacent articles in the batch use different techniques; open-question appears at most once per batch | Rewrite last 1-2 paragraphs with a different ending technique |
| B5 | **Word count preserved** | Polished article stays in the 650-750 char range (same hard requirement as initial draft); if polish reduced below 650, supplement content | Expand a middle paragraph with extra background or context, then re-polish |
| B6 | **Facts & viewpoints unchanged** | All original factual claims and core viewpoints from step 4 are still present in the polished text; nothing was fabricated during polish | Diff the two versions, restore any accidentally deleted factual content |
| B7 | **No meme-stacking / forced slang** | No piled-up internet slang; language is colloquial but natural, like chatting with a friend | Re-polish to natural tone |
| B8 | **Natural sentence rhythm** | Mix of long and short sentences; no run-on paragraphs (>150 chars per paragraph on average) | Re-polish sentence breaks |
| B9 | **Erhua clean** | Full article has no 儿化音 residue (run `clean_erhua()` final pass; verify against `_ERHUA_MAP` 24 groups + regex fallback) | Run `clean_erhua()` + manual sweep |
| B10 | **Direct paragraph entry & direct ending, sincere-conversation tone** | Every paragraph enters the topic directly (no introductory/transitional lead-in phrases); the final part states the view directly with zero summary/transition words; sentence structures are diverse with no jargon stacking or mechanical repetition; the whole article reads like a sincere conversation with the reader | Re-polish: strip transition lead-ins from paragraph openings, rewrite the ending to state the view directly, vary sentence patterns |

### Dimension C — Image Compliance (checked third)

Verify the **5 body images + 3 cover images + layout + captions**:

| # | Check Item | Pass Rule | Fail Action |
|---|-----------|----------|------------|
| C1 | **Exactly 5 body images** (or 3 if `image_count=3` explicitly set) | Count matches the configured `image_count` (default 5); not 4, not 6 | If short: continue image pipeline to next source layer; if excess: remove last group and re-layout |
| C2 | **Image resolution** | All 5 images pass: file size ≥8KB, width ≥500px, height ≥300px. People (if any) are clearly visible | Reject low-res images and fetch replacements from next pipeline layer |
| C3 | **Aspect ratio preserved** | No cropping. Pillow processing keeps original ratio (max-width 1200px downscale only, never upscale) | Re-run Pillow processing without crop step |
| C4 | **Image-relevance check** | Each image visually matches the article topic (not a generic placeholder). If Baidu fallback was used heavily, verify keyword accuracy | Refine search keywords and refetch; if 2+ images are off-topic, refetch the whole set |
| C5 | **Dynamic layout correct** | Using `calc_image_layout(total_paragraphs, 5)` rules: (a) 1 image after paragraph 1; (b) remaining 2-image groups placed with max pure-text gap ≤3 paragraphs between adjacent groups; (c) tail pure-text = 2 or 3 paragraphs; (d) no image touches the article end (tail ≥1) | Re-run layout algorithm and verify against the 4 rules |
| C6 | **Captions in built-in caption field** | Every body image's built-in caption field (`.pgc-img-caption` DOM element in the Toutiao editor) contains "图片来源于网络". **Do NOT use separate `<p>` paragraphs for captions** — write the text directly into the editor's `.pgc-img-caption` element for each image. Zero images are missing captions. After pasting HTML, iterate all `.pgc-img-caption` elements and set `textContent = '图片来源于网络'` | For any `.pgc-img-caption` that is empty or missing, set its `textContent` to "图片来源于网络" via DOM manipulation. Verify all caption elements are filled |
| C7 | **Cover images: exactly 3** | `./output/covers/` has 3 distinct JPEG cover files per article; all are ≥8KB & ≥500×300 | Regenerate covers from the best 3 of the 5 body images, or refetch extras |
| C8 | **No stale temp files** | Before upload, `output/tmp/body_img_*` must be cleaned so the current article's images are used (not leftover from a previous article) | Delete all `body_img_*` from tmp dir before extraction |
| C9 | **Source diversity recorded** | Manifest `image_source` field reports actual layer composition (e.g. `头条(1张) + 微博(3张) + 百度(1张)`); not left blank or generic | Re-run fetch with source-tracking enabled |

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

The skill includes `upload_visible.py` for uploading generated articles to the Toutiao creator platform draft box. It uses DrissionPage to drive a real browser (non-headless).

### Browser Choice: Edge over Chrome (important)

**Always use Edge** (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`) via `co.set_browser_path(...)`. Chrome repeatedly hangs during page loads in this environment (observed multiple times: page.get() never returns, no timeout fires), while Edge with the exact same code runs reliably. Before starting any upload/fix script, kill residual browser processes first (`Get-Process chrome, msedge | Stop-Process -Force`) — leftover processes from a previous hung run cause `BrowserConnectError` (user-folder conflict).

### Login Handling

`ensure_toutiao_login.py` validates cookies before upload. If cookies are missing/expired, it **automatically opens a visible browser login page for the user to log in manually** (QR / phone / WeChat), then auto-saves the fresh cookies to `toutiao_cookies.json` (40 entries) for subsequent runs. Cookie injection format: `page.set.cookies({"name": k, "value": v, "domain": ".toutiao.com", "path": "/"})` — inject after visiting any `mp.toutiao.com` page, then reload. Injecting raw cookie-list dicts without `domain` silently fails (0 cookies injected).

### Upload Flow

0. **Pre-upload self-check (MANDATORY — runs BEFORE opening the publish page)**: Execute the full A+B+C self-check above for this specific article. If any dimension fails, enter the regenerate loop. **Do NOT open the browser or call save API until self-check passes.**
1. **Login**: Load cookies from `toutiao_cookies.json` and navigate to `mp.toutiao.com`.
2. **Create new article**: Open the publish page, wait for the ProseMirror editor to mount.
3. **Fill title**: Use native `value setter` + `input`/`change` events to trigger React state update (DrissionPage's `input()` doesn't work for React-controlled title textarea).
4. **Upload body images**: Two-stage approach:
   - Stage 1: Upload all images one-by-one by pasting Blob via `ClipboardEvent('paste')`, capturing returned server URLs.
   - Stage 2: Set all content (text + images) at once via ProseMirror `view.dispatch()` API with properly structured image nodes.
5. **Upload covers**: By default `SKIP_COVER=0` uploads 3 covers via file input. Set `SKIP_COVER=1` to skip.
6. **Pre-save re-check (lightweight, in-page)**: Before clicking Save / calling the publish API, do a quick DOM check: (a) title has 2 commas / 3 segments and 20-30 chars, and matches the user-selected title from the title-candidates pause; (b) 5 images present in DOM; (c) each image's `.pgc-img-caption` element contains "图片来源于网络" (NOT a separate `<p>` paragraph). If any mismatch, fix in-page before saving.
7. **Fill all image captions (MANDATORY)**: After pasting HTML content into the ProseMirror editor, the Toutiao editor auto-creates `.pgc-img-caption` elements for each image but leaves them empty. **Iterate ALL `.pgc-img-caption` elements and set `textContent = '图片来源于网络'`**. Do NOT use `<figure>/<figcaption>`, `<p>图片来源于网络</p>`, or any separate text paragraph for captions — the editor splits these into standalone paragraphs. Captions must ONLY live in the `.pgc-img-caption` DOM element that the editor generates per image.
8. **Save / auto-save to draft box**: Trigger save (or let auto-save commit). The save request must include: `save='1'`, `draft_form_data={"coverType":3}`, `pgc_feed_covers=[3 cover URLs]`.
9. **Verify**: Check draft list for the article; confirm the saved article's title matches and images are present.

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

`batch_upload_tt.py` reads `batch_manifest_tt.json` and uploads each article sequentially. **For every single article in the manifest, the pre-upload A+B+C self-check runs BEFORE the upload subprocess is spawned.** If an article fails self-check after 3 regenerate attempts, it is skipped (logged) and the batch moves to the next article — the batch never stalls on one failing article.

Supports a command-line start index for resuming after interruptions:

```bash
python batch_upload_tt.py 4   # Resume from 4th article (self-check still runs for 4th+)
```

Each article upload runs as a subprocess with a 180s timeout. Logs are written to `batch_upload_tt.log` with timestamps, including self-check pass/fail per article and (if applicable) which dimension failed and what regeneration step was run.

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
- **Pre-upload self-check failure loop**: If an article fails opening / polish / image compliance check after 3 regenerate attempts, it is skipped (logged) and the batch proceeds — one bad article never blocks the rest.
- If batch upload stalls: use `python batch_upload_tt.py <start_index>` to resume (self-check still runs for resumed articles).
- **Batch-upload "timeout" does NOT mean failure**: `batch_upload_tt.py` reports 超时 per article when the subprocess exceeds the wait limit, but the article is often already saved (cover upload is slow, ~3min per cover). Always verify the actual draft box state via the API (`/mp/agw/article/list` and `/mp/agw/creator_center/draft_list` with cookie header) before re-uploading — otherwise you create duplicate drafts.
- **Title may silently fail to save (no-title draft)**: in rare cases the React native-setter title fill does not get committed to the saved draft, producing a draft with empty title. Fix flow: query `draft_list` API to get the draft's `gid`, open the edit page, re-fill the title via the same native setter, click 存草稿. **Caution**: `https://mp.toutiao.com/profile_v4/graphic/publish?draft_id=<gid>&article_edit=1` does NOT reliably load the existing draft content (loads a fresh empty editor) — editing via this URL can create empty shell drafts. When patching a title, verify the editor actually loaded the draft body first; delete accidental empty-shell drafts via `POST /mp/agw/article/delete` (form: `pgc_id`, `group_id`).
- **Draft box verification API** (works without browser): `GET https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=15&type=&source=0&_signature=` and `GET https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=20&app_id=1231` with `Cookie` header built from `toutiao_cookies.json` (dict form: `"; ".join(f"{k}={v}")`). Returns titles, `is_draft`, `create_time`, `article_url` — use this as the source of truth after uploads.
- If cover upload fails: article content is still saved; covers can be manually added later. Set `SKIP_COVER=1` to skip cover upload entirely.
- **Stale temp images**: `upload_visible.py` saves body images to `output/tmp/body_img_N.jpg` before uploading. If these files persist from a previous article, they will be reused by mistake, causing the wrong images to appear in the new article. Fixed: all `body_img_*` files are cleared before each upload, forcing fresh extraction from the current article's base64 data.
- **Baidu image encrypted objURL**: Some Baidu image results return encrypted `objURL` that cannot be directly downloaded. Fixed: prioritize `middleURL`/`thumbURL` (always accessible) over `objURL`.
