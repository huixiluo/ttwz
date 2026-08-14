# 微博热搜图文改写应用实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建本地 Web 应用，从公开微博热搜选择娱乐、体育或社会类选题，基于可追溯资讯生成去 AI 味的约 600 字图文稿，并在每两段后插入处理后的来源图片。

**Architecture:** FastAPI 提供服务端渲染页面与 JSON 接口。采集、正文回退、改写规则、图片处理和导出分别封装为小型服务；路由层只协调输入和输出。所有外部网络和 DashScope 调用通过依赖注入传入，测试以本地 fixture 和假客户端覆盖。

**Tech Stack:** Python 3.12、FastAPI、Jinja2、Pydantic、HTTPX、BeautifulSoup4、Pillow、DashScope SDK、pytest、pytest-asyncio。

## 全局约束

- 仅抓取公开页面，不绕过登录、验证码、访问限制或付费墙。
- 一次选择 1–3 个选题；每个选题独立成稿，不能混合事实或图片。
- 成稿固定 6 段、总长 550–650 字、单段不超过 150 字；第 2、4、6 段后各插 1 张来源处理图。
- 图片只来自实际采用的原始资讯，必须经过 16:9 裁剪和轻度滤镜；缺少 3 张有效图时拒绝生成。
- 改写只使用已提取的来源事实；禁止编造、模板化 AI 话术、空泛升华与未经支持的情绪判断。
- `.env` 的 `DASHSCOPE_API_KEY` 优先于界面临时 API Key；临时值不可写入磁盘、日志或导出文件。
- 测试不得访问微博、媒体网站或 DashScope。

---

## 文件结构

| 文件 | 责任 |
| --- | --- |
| `pyproject.toml` | 固定运行与测试依赖、pytest 配置。 |
| `.env.example` | 仅提供 `DASHSCOPE_API_KEY` 配置样例。 |
| `src/weibo_writer/models.py` | 选题、来源、成稿和图片处理的 Pydantic 数据模型。 |
| `src/weibo_writer/hot_search.py` | 公开热搜页面解析及指定类别筛选。 |
| `src/weibo_writer/sources.py` | 微博正文优先、公开报道回退的资讯解析。 |
| `src/weibo_writer/writer.py` | DashScope 提示词、成稿验证和去 AI 味检查。 |
| `src/weibo_writer/images.py` | 下载校验、16:9 裁剪、滤镜和输出文件。 |
| `src/weibo_writer/exporter.py` | 文稿与图片排版为 HTML/Markdown。 |
| `src/weibo_writer/app.py` | FastAPI 工厂、依赖装配和页面/API 路由。 |
| `src/weibo_writer/templates/index.html` | 热搜选择、密钥输入、错误与成稿展示。 |
| `src/weibo_writer/static/app.css` | 小屏可用的本地页面样式。 |
| `tests/fixtures/*.html` | 固定热搜、微博和媒体页测试素材。 |
| `tests/test_*.py` | 对应服务与端到端接口测试。 |

---

### Task 1: 项目骨架与领域模型

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/weibo_writer/__init__.py`
- Create: `src/weibo_writer/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `Topic`, `SourceArticle`, `ProcessedImage`, `GeneratedArticle`；后续任务只使用这四个模型传递数据。
- Produces: `ArticleValidationError`，供改写校验和路由层转换为可读错误。

- [ ] **Step 1: 写入失败测试**

```python
from pydantic import ValidationError
import pytest

from weibo_writer.models import GeneratedArticle, Topic


def test_topic_rejects_unapproved_category():
    with pytest.raises(ValidationError):
        Topic(title="任意热词", rank=1, hot_value="123", url="https://s.weibo.com", category="财经")


def test_generated_article_requires_six_short_paragraphs():
    with pytest.raises(ValidationError):
        GeneratedArticle(title="测试", paragraphs=["第一段"] * 5, source_urls=["https://example.com"])
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_models.py -q`

Expected: FAIL，提示 `weibo_writer` 或模型尚未定义。

- [ ] **Step 3: 实现最小模型与项目配置**

```python
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator

Category = Literal["娱乐", "体育", "社会"]


class Topic(BaseModel):
    title: str = Field(min_length=2)
    rank: int = Field(ge=1)
    hot_value: str
    url: HttpUrl
    category: Category


class SourceArticle(BaseModel):
    title: str
    body: str = Field(min_length=120)
    url: HttpUrl
    publisher: str
    image_urls: list[HttpUrl]


class ProcessedImage(BaseModel):
    path: str
    source_url: HttpUrl
    alt: str


class GeneratedArticle(BaseModel):
    title: str
    paragraphs: list[str] = Field(min_length=6, max_length=6)
    source_urls: list[HttpUrl] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_paragraphs(self):
        if any(len(item) > 150 for item in self.paragraphs):
            raise ValueError("每段不得超过150字")
        total = sum(len(item) for item in self.paragraphs)
        if not 550 <= total <= 650:
            raise ValueError("全文必须为550至650字")
        return self


class ArticleValidationError(ValueError):
    pass
```

`pyproject.toml` 配置 `src` 包路径、运行依赖与 `pytest` 的 `asyncio_mode = "auto"`；`.env.example` 仅包含 `DASHSCOPE_API_KEY=`。

- [ ] **Step 4: 验证模型测试通过**

Run: `python -m pytest tests/test_models.py -q`

Expected: PASS，两个测试均通过。

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml .env.example src/weibo_writer tests/test_models.py
git commit -m "feat: add writer domain models"
```

### Task 2: 热搜解析与类别筛选

**Files:**
- Create: `src/weibo_writer/hot_search.py`
- Create: `tests/fixtures/weibo_hot_search.html`
- Create: `tests/test_hot_search.py`

**Interfaces:**
- Consumes: `Topic`。
- Produces: `parse_hot_search(html: str) -> list[Topic]` 与 `filter_topics(topics: list[Topic], category: Category) -> list[Topic]`。
- Produces: `HotSearchClient.fetch() -> list[Topic]`，仅供应用运行时调用，构造函数接收 `httpx.AsyncClient`。

- [ ] **Step 1: 写入失败测试**

```python
from pathlib import Path

from weibo_writer.hot_search import filter_topics, parse_hot_search


def test_parse_hot_search_keeps_supported_categories_only():
    html = Path("tests/fixtures/weibo_hot_search.html").read_text(encoding="utf-8")
    topics = parse_hot_search(html)
    assert [topic.title for topic in topics] == ["电影新片首映", "国家队夺冠", "城市暖心救助"]


def test_filter_topics_returns_only_requested_category():
    html = Path("tests/fixtures/weibo_hot_search.html").read_text(encoding="utf-8")
    assert [item.title for item in filter_topics(parse_hot_search(html), "体育")] == ["国家队夺冠"]
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_hot_search.py -q`

Expected: FAIL，提示 `weibo_writer.hot_search` 尚不存在。

- [ ] **Step 3: 实现最小解析器**

```python
def parse_hot_search(html: str) -> list[Topic]:
    soup = BeautifulSoup(html, "html.parser")
    topics = []
    for row in soup.select("tr[data-category]"):
        category = row["data-category"]
        if category not in {"娱乐", "体育", "社会"}:
            continue
        link = row.select_one("a.topic")
        rank = int(row.select_one("td.rank").get_text(strip=True))
        topics.append(Topic(
            title=link.get_text(strip=True), rank=rank,
            hot_value=row.select_one("td.hot").get_text(strip=True),
            url=urljoin("https://s.weibo.com", link["href"]), category=category,
        ))
    return topics


def filter_topics(topics: list[Topic], category: Category) -> list[Topic]:
    return [topic for topic in topics if topic.category == category]
```

`HotSearchClient.fetch()` 使用固定 User-Agent 和 10 秒超时请求公开热搜页；非 200、网络异常或解析结果为空时抛出 `RuntimeError`，由路由层展示。

- [ ] **Step 4: 验证热搜测试通过**

Run: `python -m pytest tests/test_hot_search.py -q`

Expected: PASS，fixture 中三个允许类别可被解析和筛选。

- [ ] **Step 5: 提交**

```bash
git add src/weibo_writer/hot_search.py tests/fixtures/weibo_hot_search.html tests/test_hot_search.py
git commit -m "feat: parse public weibo hot topics"
```

### Task 3: 原始资讯与图片来源解析

**Files:**
- Create: `src/weibo_writer/sources.py`
- Create: `tests/fixtures/weibo_post.html`
- Create: `tests/fixtures/news_article.html`
- Create: `tests/test_sources.py`

**Interfaces:**
- Consumes: `Topic`, `SourceArticle`。
- Produces: `SourceResolver.resolve(topic: Topic) -> SourceArticle`。
- `SourceResolver` 构造函数接收两个 async callable：`fetch_weibo(topic) -> str` 和 `fetch_news(topic) -> str`；先调用微博，再调用新闻回退。

- [ ] **Step 1: 写入失败测试**

```python
from pathlib import Path
import pytest

from weibo_writer.models import Topic
from weibo_writer.sources import SourceResolver


@pytest.mark.asyncio
async def test_resolver_uses_public_news_when_weibo_body_is_unavailable():
    async def blocked_weibo(topic):
        return "<html><title>访问受限</title></html>"

    async def news(topic):
        return Path("tests/fixtures/news_article.html").read_text(encoding="utf-8")

    resolver = SourceResolver(fetch_weibo=blocked_weibo, fetch_news=news)
    article = await resolver.resolve(Topic(
        title="国家队夺冠", rank=2, hot_value="100", url="https://s.weibo.com", category="体育",
    ))
    assert article.publisher == "示例体育报"
    assert len(article.image_urls) == 3
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_sources.py -q`

Expected: FAIL，提示 `SourceResolver` 尚未定义。

- [ ] **Step 3: 实现正文优先与回退解析**

```python
class SourceResolver:
    def __init__(self, fetch_weibo, fetch_news):
        self.fetch_weibo = fetch_weibo
        self.fetch_news = fetch_news

    async def resolve(self, topic: Topic) -> SourceArticle:
        weibo_html = await self.fetch_weibo(topic)
        article = parse_weibo_post(weibo_html, topic)
        if article is not None and len(article.image_urls) >= 3:
            return article
        news_html = await self.fetch_news(topic)
        article = parse_news_article(news_html, topic)
        if article is None:
            raise RuntimeError("未能取得可公开访问且内容完整的原始资讯")
        if len(article.image_urls) < 3:
            raise RuntimeError("所采用资讯不足三张可处理图片")
        return article
```

`parse_weibo_post` 与 `parse_news_article` 只提取正文中的可见段落和 `http/https` 图片，拼接后正文少于 120 字、图片少于 3 张或存在访问限制标记即返回 `None`。运行时 fetcher 只访问公开 URL；新闻回退的 URL、标题与出版方必须随 `SourceArticle` 返回。

- [ ] **Step 4: 验证来源回退测试通过**

Run: `python -m pytest tests/test_sources.py -q`

Expected: PASS，微博受限时使用 fixture 新闻正文和三张图片。

- [ ] **Step 5: 提交**

```bash
git add src/weibo_writer/sources.py tests/fixtures/weibo_post.html tests/fixtures/news_article.html tests/test_sources.py
git commit -m "feat: resolve source articles with fallback"
```

### Task 4: DashScope 改写与去 AI 味校验

**Files:**
- Create: `src/weibo_writer/writer.py`
- Create: `tests/test_writer.py`

**Interfaces:**
- Consumes: `Topic`, `SourceArticle`, `GeneratedArticle`。
- Produces: `build_prompt(topic: Topic, source: SourceArticle) -> str`、`validate_style(article: GeneratedArticle) -> None`、`ArticleWriter.generate(topic, source, api_key) -> GeneratedArticle`。
- `ArticleWriter` 构造函数接收 `complete(prompt: str, api_key: str) -> str`；生产实现封装 DashScope 调用，测试提供固定字符串。

- [ ] **Step 1: 写入失败测试**

```python
import pytest

from weibo_writer.models import ArticleValidationError, GeneratedArticle
from weibo_writer.writer import validate_style


def test_style_validator_rejects_repetitive_ai_transition_phrases():
    paragraphs = ["具体事实" * 24 for _ in range(6)]
    paragraphs[1] = "值得一提的是，" + "具体事实" * 22
    article = GeneratedArticle(title="测试", paragraphs=paragraphs, source_urls=["https://example.com"])
    with pytest.raises(ArticleValidationError, match="模板化表达"):
        validate_style(article)
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_writer.py -q`

Expected: FAIL，提示 `validate_style` 尚未定义。

- [ ] **Step 3: 实现提示词、格式解析与一次重写**

```python
FORBIDDEN_PHRASES = ("值得一提的是", "不难发现", "在这个信息爆炸的时代")


def validate_style(article: GeneratedArticle) -> None:
    if any(phrase in paragraph for phrase in FORBIDDEN_PHRASES for paragraph in article.paragraphs):
        raise ArticleValidationError("检测到模板化表达")
    openings = [paragraph[:12] for paragraph in article.paragraphs]
    if len(set(openings)) < 5:
        raise ArticleValidationError("段落句式重复")


def build_prompt(topic: Topic, source: SourceArticle) -> str:
    return f"""仅依据以下来源事实重写新闻，不得补造事实：\n{source.body}\n
围绕《{topic.title}》写六段中文成稿：全文550-650字，每段不超过150字；保留事实，补充来源能支持的背景；语气积极克制；第六段提出非煽动性讨论点；禁用模板化过渡语、空泛升华、机械排比和AI口吻。仅返回六个以空行分隔的段落。"""
```

`ArticleWriter.generate` 从 `.env` 或请求临时值取得 API Key，调用模型后按空行拆成段落并构造 `GeneratedArticle`。格式或风格不通过时，以“保持相同事实、修正具体错误”为提示仅重试一次；第二次失败抛出 `ArticleValidationError`，绝不返回未验证文章。

- [ ] **Step 4: 验证改写测试通过**

Run: `python -m pytest tests/test_writer.py -q`

Expected: PASS，模板化句式被识别并拒绝。

- [ ] **Step 5: 提交**

```bash
git add src/weibo_writer/writer.py tests/test_writer.py
git commit -m "feat: validate natural article rewrites"
```

### Task 5: 图片处理与图文导出

**Files:**
- Create: `src/weibo_writer/images.py`
- Create: `src/weibo_writer/exporter.py`
- Create: `tests/fixtures/source.jpg`
- Create: `tests/test_images.py`
- Create: `tests/test_exporter.py`

**Interfaces:**
- Consumes: `SourceArticle`, `ProcessedImage`, `GeneratedArticle`。
- Produces: `process_images(source, download, output_dir) -> list[ProcessedImage]`、`render_html(article, images, sources) -> str`、`render_markdown(article, images, sources) -> str`。
- `process_images` 接收 download callable，必须返回图片二进制；不直接依赖网络客户端。

- [ ] **Step 1: 写入失败测试**

```python
from io import BytesIO
from PIL import Image

from weibo_writer.images import transform_image


def test_transform_image_outputs_clear_16_by_9_jpeg():
    source = Image.new("RGB", (1200, 1200), color=(70, 120, 180))
    output = transform_image(source)
    assert output.size == (1200, 675)
    assert output.mode == "RGB"
```

```python
from weibo_writer.exporter import render_html


def test_html_inserts_images_after_every_two_paragraphs(article, images, sources):
    html = render_html(article, images, sources)
    assert html.index(images[0].path) > html.index(article.paragraphs[1])
    assert html.index(images[1].path) > html.index(article.paragraphs[3])
    assert html.index(images[2].path) > html.index(article.paragraphs[5])
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_images.py tests/test_exporter.py -q`

Expected: FAIL，提示 `transform_image` 和 `render_html` 尚未定义。

- [ ] **Step 3: 实现裁剪、滤镜与排版**

```python
def transform_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    target_height = round(width * 9 / 16)
    if height < target_height:
        target_width = round(height * 16 / 9)
        left = (width - target_width) // 2
        image = image.crop((left, 0, left + target_width, height))
    else:
        top = (height - target_height) // 2
        image = image.crop((0, top, width, top + target_height))
    return ImageEnhance.Color(ImageEnhance.Contrast(ImageEnhance.Brightness(image).enhance(1.04)).enhance(1.06)).enhance(0.96)
```

`process_images` 逐张验证内容类型与 Pillow 可读性，处理前三张不同 URL 的来源图，保存为 `data/outputs/<uuid>/image-1.jpg` 到 `image-3.jpg`。`render_html` 按“两个 `<p>` + 一个 `<img>`”重复三次，末尾列出来源标题、URL 与抓取时间；`render_markdown` 使用同样顺序。

- [ ] **Step 4: 验证图片与导出测试通过**

Run: `python -m pytest tests/test_images.py tests/test_exporter.py -q`

Expected: PASS，输出为 16:9 RGB 图，三张图插入位置正确。

- [ ] **Step 5: 提交**

```bash
git add src/weibo_writer/images.py src/weibo_writer/exporter.py tests/fixtures/source.jpg tests/test_images.py tests/test_exporter.py
git commit -m "feat: process source images and export articles"
```

### Task 6: FastAPI 页面与完整流程

**Files:**
- Create: `src/weibo_writer/app.py`
- Create: `src/weibo_writer/templates/index.html`
- Create: `src/weibo_writer/static/app.css`
- Create: `tests/test_app.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `HotSearchClient`, `SourceResolver`, `ArticleWriter`, `process_images`, `render_html`。
- Produces: `create_app(services: Services | None = None) -> FastAPI`、`GET /`、`POST /api/topics/refresh`、`POST /api/articles/generate`、`GET /downloads/{job_id}.html`。
- `POST /api/articles/generate` 接受 `topics: list[Topic]` 和可选 `api_key: str | None`；超过 3 条、空选择或无有效 API Key 返回 422。

- [ ] **Step 1: 写入失败测试**

```python
from fastapi.testclient import TestClient

from weibo_writer.app import Services, create_app


def test_refresh_returns_only_approved_categories(fake_services):
    client = TestClient(create_app(fake_services))
    response = client.post("/api/topics/refresh")
    assert response.status_code == 200
    assert {item["category"] for item in response.json()["topics"]} <= {"娱乐", "体育", "社会"}


def test_generate_rejects_more_than_three_topics(fake_services):
    client = TestClient(create_app(fake_services))
    response = client.post("/api/articles/generate", json={"topics": [fake_services.topic] * 4})
    assert response.status_code == 422
```

- [ ] **Step 2: 验证测试确实失败**

Run: `python -m pytest tests/test_app.py -q`

Expected: FAIL，提示 `create_app` 尚未定义。

- [ ] **Step 3: 实现路由与页面**

```python
def create_app(services: Services | None = None) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.post("/api/topics/refresh")
    async def refresh_topics():
        return {"topics": [item.model_dump(mode="json") for item in await app.state.services.hot_search.fetch()]}

    @app.post("/api/articles/generate")
    async def generate(payload: GenerateRequest):
        if not 1 <= len(payload.topics) <= 3:
            raise HTTPException(422, "请选择1至3条热搜")
        return await generate_articles(payload, app.state.services)

    return app
```

页面必须包含三个类别筛选、复选框、临时密钥密码框、刷新与生成按钮、加载/失败状态、来源列表、文章与图片预览、复制 Markdown 按钮和 HTML 下载链接。界面不在浏览器存储 API Key；服务器日志不记录请求体中的 key。将 `weibo-writer = "weibo_writer.app:run"` 写入 `pyproject.toml` 脚本入口，使用 `uvicorn` 启动。

- [ ] **Step 4: 验证接口与全量测试通过**

Run: `python -m pytest -q`

Expected: PASS，所有模型、采集、回退、风格、图片、导出和路由测试通过。

- [ ] **Step 5: 本地手工验收**

Run: `python -m uvicorn weibo_writer.app:create_app --factory --host 127.0.0.1 --port 8000`

Expected: 浏览器访问 `http://127.0.0.1:8000` 后可完成刷新、筛选、选择、临时/环境变量密钥生成、查看三张处理图和下载 HTML；外部不可达时显示来源错误，不返回编造内容。

- [ ] **Step 6: 提交**

```bash
git add src/weibo_writer/app.py src/weibo_writer/templates/index.html src/weibo_writer/static/app.css tests/test_app.py pyproject.toml
git commit -m "feat: add local hot news writer web app"
```

## 计划自检

- 规格中“公开热搜、正文回退、不可编造、来源可追溯”由 Task 2、Task 3 与 Task 6 覆盖。
- “六段、550–650 字、每段不超过 150 字、去 AI 味、一次重写”由 Task 1 与 Task 4 覆盖。
- “三张资讯来源图片、裁剪滤镜、每两段插图”由 Task 3 与 Task 5 覆盖。
- “`.env` 与临时密钥、临时不落盘”由 Task 4 与 Task 6 覆盖。
- 已检查接口名、模型名和类型：后续任务均使用 Task 1 定义的 `Topic`、`SourceArticle`、`ProcessedImage`、`GeneratedArticle`，不存在未定义占位接口。
