# -*- coding: utf-8 -*-
"""批量上传6篇文章到头条草稿箱（跳过封面，后续手动补）
依次读取 batch_manifest.json 中的每篇文章，写入 single_manifest.json 后调用 upload_visible.main()
"""
import os
import json
import time
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BATCH_MANIFEST = os.path.join(BASE_DIR, "output", "batch_manifest.json")
SINGLE_MANIFEST = os.path.join(BASE_DIR, "single_manifest.json")


def main():
    with open(BATCH_MANIFEST, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total = len(articles)
    print("=" * 60)
    print(f"批量上传 {total} 篇文章到头条草稿箱（跳过封面）")
    print("=" * 60)

    # 设置环境变量跳过封面上传
    env = os.environ.copy()
    env["SKIP_COVER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"  # 禁用输出缓冲

    success = 0
    for i, art in enumerate(articles, 1):
        title = art.get("title", "")[:30]
        print(f"\n{'='*60}")
        print(f"[{i}/{total}] 上传：{title}")
        print("=" * 60, flush=True)

        # 写入单篇清单
        with open(SINGLE_MANIFEST, "w", encoding="utf-8") as f:
            json.dump([art], f, ensure_ascii=False, indent=2)

        # 清理旧临时图片（避免复用错误的缓存）
        tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
        if os.path.exists(tmp_dir):
            for fn in os.listdir(tmp_dir):
                if fn.startswith("body_img_"):
                    try:
                        os.remove(os.path.join(tmp_dir, fn))
                    except Exception:
                        pass

        # 清理浏览器进程
        subprocess.run(
            ["powershell", "-Command",
             "taskkill /F /IM chrome.exe 2>$null; taskkill /F /IM chromedriver.exe 2>$null; Start-Sleep -Seconds 2"],
            capture_output=True, timeout=30
        )

        # 运行 upload_visible.py（实时输出，不捕获）
        result = subprocess.run(
            [sys.executable, "-u", "upload_visible.py"],
            cwd=BASE_DIR,
            env=env,
            timeout=180,
        )

        if result.returncode == 0:
            success += 1
            print(f"\n  >> [{i}/{total}] 上传完成")
        else:
            print(f"\n  >> [{i}/{total}] 上传异常 (returncode={result.returncode})")

        # 篇间间隔
        if i < total:
            time.sleep(3)

    print(f"\n{'='*60}")
    print(f"批量上传完成：{success}/{total} 篇成功")
    print("注意：封面图未上传，需手动补充")
    print("=" * 60)


if __name__ == "__main__":
    main()
