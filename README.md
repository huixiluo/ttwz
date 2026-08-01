# 微博热搜改写工具 (ttwz)

获取微博热搜 → DeepSeek 改写（去AI味、爆款标题）→ 百度图片搜索配图 → Pillow 处理 → 输出 HTML

## 功能

- 自动获取微博实时热搜榜（模拟访客系统，无需登录）
- 按类别筛选（娱乐/体育/社会）
- 调用 DeepSeek 生成约600字原创文章 + 爆款标题（≤25字）
- 文章风格去AI味：口语化、句子长短错落、禁机械关联词
- 百度图片搜索获取3张配图，Pillow 裁剪+滤镜处理
- 每两段插入一张图片，输出独立 HTML 文件

## 快速开始

```bash
# 1. 安装依赖
pip install requests Pillow

# 2. 复制配置文件并填写 API Key
cp config.example.json config.json
# 编辑 config.json，填入你的 DeepSeek API Key

# 3. 运行
python hot_news_writer.py 娱乐   # 娱乐类
python hot_news_writer.py 体育   # 体育类
python hot_news_writer.py 社会   # 社会类
```

## 配置说明

编辑 `config.json`：

```json
{
  "api_key": "你的DeepSeek API Key",
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "model": "deepseek-chat",
  "output_dir": "./output",
  "image_count": 3
}
```

## 预览产出

```bash
python -m http.server 8000 --directory output
```

浏览器打开 `http://localhost:8000/` 查看所有文章。

## 文章要求

- **标题**：≤25字、爆款、不标题党、不偏向特定人物、不编造假设性事实
- **正文**：约600字、4-5段（每段≤150字）、积极正能量、引发共鸣
- **风格**：去AI味、口语化、句子长短错落、允许个人视角
- **配图**：3张、每两段一张、16:9裁剪、滤镜增强

## 依赖

- Python 3.10+
- requests, Pillow
- DeepSeek API Key

## 文件结构

```
ttwz/
├── hot_news_writer.py      # 主脚本
├── config.example.json     # 配置示例
├── config.json             # 实际配置（gitignore，不提交）
├── output/                 # 产出目录
└── .trae/
    └── skills/
        └── weibo-hotspot-writer/
            └── SKILL.md    # TRAE Skill 定义
```
