# -*- coding: utf-8 -*-
"""批量上传头条热榜文章到头条草稿箱
依次读取 output/batch_manifest_tt.json 中的每篇文章，写入 single_manifest.json 后调用 upload_visible.main()
支持断点续传：python batch_upload_tt.py 4  （从第4篇开始）
"""
import os
import json
import time
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BATCH_MANIFEST = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
SINGLE_MANIFEST = os.path.join(BASE_DIR, "single_manifest.json")
BATCH_LOG = os.path.join(BASE_DIR, "batch_upload_tt.log")


def blog(msg):
    with open(BATCH_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def main():
    start_index = 1
    if len(sys.argv) > 1:
        try:
            start_index = int(sys.argv[1])
        except ValueError:
            pass

    mode = "a" if start_index > 1 else "w"
    with open(BATCH_LOG, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("")
        else:
            f.write(f"\n--- 断点续传：从第{start_index}篇开始 ---\n")

    with open(BATCH_MANIFEST, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total = len(articles)
    blog(f"批量上传 {total} 篇头条热榜文章到头条草稿箱，从第{start_index}篇开始")
    print("=" * 60, flush=True)
    print(f"批量上传 {total} 篇头条热榜文章到头条草稿箱（从第{start_index}篇开始）", flush=True)
    print("=" * 60, flush=True)

    env = os.environ.copy()
    env["SKIP_COVER"] = "0"
    env["PYTHONUNBUFFERED"] = "1"

    success = 0
    for i, art in enumerate(articles, 1):
        if i < start_index:
            continue
        title = art.get("title", "")[:30]
        blog(f"[{i}/{total}] 开始上传：{title}")
        print(f"\n{'='*60}", flush=True)
        print(f"[{i}/{total}] 上传：{title}", flush=True)
        print("=" * 60, flush=True)

        with open(SINGLE_MANIFEST, "w", encoding="utf-8") as f:
            json.dump([art], f, ensure_ascii=False, indent=2)

        # 清理旧临时图片
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

        blog(f"[{i}/{total}] 调用 subprocess: {sys.executable} -u upload_visible.py")
        upload_log = os.path.join(BASE_DIR, "upload_subprocess_tt.log")
        try:
            with open(upload_log, "w", encoding="utf-8") as logf:
                result = subprocess.run(
                    [sys.executable, "-u", "upload_visible.py"],
                    cwd=BASE_DIR,
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    timeout=180,
                )
            with open(upload_log, "r", encoding="utf-8") as logf:
                for line in logf:
                    blog(f"  [stdout] {line.rstrip()}")
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

        if i < total:
            time.sleep(3)

    print()
    print("=" * 60, flush=True)
    print(f"批量上传结束：成功 {success}/{total - start_index + 1}，日志：{BATCH_LOG}", flush=True)
    print("=" * 60, flush=True)
    blog(f"批量上传结束：成功 {success}/{total - start_index + 1}")


if __name__ == "__main__":
    main()
