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
BATCH_LOG = os.path.join(BASE_DIR, "batch_upload.log")


def blog(msg):
    """文件日志，绕过终端输出捕获问题"""
    with open(BATCH_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def main():
    # 清空旧日志
    with open(BATCH_LOG, "w", encoding="utf-8") as f:
        f.write("")

    with open(BATCH_MANIFEST, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total = len(articles)
    blog(f"批量上传 {total} 篇文章到头条草稿箱（跳过封面）")
    print("=" * 60, flush=True)
    print(f"批量上传 {total} 篇文章到头条草稿箱（跳过封面）", flush=True)
    print("=" * 60, flush=True)

    # 设置环境变量跳过封面上传
    env = os.environ.copy()
    env["SKIP_COVER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"  # 禁用输出缓冲

    success = 0
    for i, art in enumerate(articles, 1):
        title = art.get("title", "")[:30]
        blog(f"[{i}/{total}] 开始上传：{title}")
        print(f"\n{'='*60}", flush=True)
        print(f"[{i}/{total}] 上传：{title}", flush=True)
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

        # 运行 upload_visible.py（捕获输出到日志文件）
        blog(f"[{i}/{total}] 调用 subprocess: {sys.executable} -u upload_visible.py")
        try:
            result = subprocess.run(
                [sys.executable, "-u", "upload_visible.py"],
                cwd=BASE_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            # 记录子进程输出到日志
            if result.stdout:
                for line in result.stdout.splitlines():
                    blog(f"  [stdout] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    blog(f"  [stderr] {line}")
            blog(f"[{i}/{total}] subprocess返回 returncode={result.returncode}")

            if result.returncode == 0:
                success += 1
                print(f"\n  >> [{i}/{total}] 上传完成", flush=True)
                blog(f"[{i}/{total}] 上传完成")
            else:
                print(f"\n  >> [{i}/{total}] 上传异常 (returncode={result.returncode})", flush=True)
                blog(f"[{i}/{total}] 上传异常 (returncode={result.returncode})")
        except subprocess.TimeoutExpired:
            print(f"\n  >> [{i}/{total}] 超时", flush=True)
            blog(f"[{i}/{total}] 超时（180s）")
        except Exception as e:
            print(f"\n  >> [{i}/{total}] 异常: {e}", flush=True)
            blog(f"[{i}/{total}] 异常: {e}")

        # 篇间间隔
        if i < total:
            time.sleep(3)

    blog(f"批量上传完成：{success}/{total} 篇成功")
    print(f"\n{'='*60}", flush=True)
    print(f"批量上传完成：{success}/{total} 篇成功", flush=True)
    print("注意：封面图未上传，需手动补充", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
