# -*- coding: utf-8 -*-
"""批量上传文章到头条草稿箱（Linux headless 版）
依次读取 batch_manifest.json 中的每篇文章，写入 single_manifest.json 后调用 upload_linux.py
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


def cleanup_chrome():
    """清理可能残留的 chromium 进程（Linux）"""
    try:
        subprocess.run(
            ["pkill", "-f", "chrome-linux64/chrome"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass
    time.sleep(2)


def main():
    # 支持命令行参数指定起始索引（从1开始），用于断点续传
    start_index = 1
    if len(sys.argv) > 1:
        try:
            start_index = int(sys.argv[1])
        except ValueError:
            pass

    # 追加模式：如果是断点续传（start_index > 1），不清空旧日志
    mode = "a" if start_index > 1 else "w"
    with open(BATCH_LOG, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("")
        else:
            f.write(f"\n--- 断点续传：从第{start_index}篇开始 ---\n")

    with open(BATCH_MANIFEST, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total = len(articles)
    blog(f"批量上传 {total} 篇文章到头条草稿箱（Linux headless，跳过封面），从第{start_index}篇开始")
    print("=" * 60, flush=True)
    print(f"批量上传 {total} 篇文章到头条草稿箱（从第{start_index}篇开始）", flush=True)
    print("=" * 60, flush=True)

    # 设置环境变量跳过封面上传
    env = os.environ.copy()
    env["SKIP_COVER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    success = 0
    for i, art in enumerate(articles, 1):
        if i < start_index:
            continue  # 跳过已上传的
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

        # 清理浏览器进程（Linux）
        cleanup_chrome()

        # 运行 upload_linux.py（输出重定向到日志文件，避免管道死锁）
        blog(f"[{i}/{total}] 调用 subprocess: {sys.executable} -u upload_linux.py")
        upload_log = os.path.join(BASE_DIR, "upload_subprocess.log")
        try:
            with open(upload_log, "w", encoding="utf-8") as logf:
                result = subprocess.run(
                    [sys.executable, "-u", "upload_linux.py"],
                    cwd=BASE_DIR,
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    timeout=600,  # 10分钟超时（保存可能需要多次重试）
                )
            # 读取子进程输出到日志
            with open(upload_log, "r", encoding="utf-8") as logf:
                content = logf.read()
                blog(f"[{i}/{total}] subprocess输出 (returncode={result.returncode}):\n{content[-3000:]}")
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
            blog(f"[{i}/{total}] 超时（300s）")
        except Exception as e:
            print(f"\n  >> [{i}/{total}] 异常: {e}", flush=True)
            blog(f"[{i}/{total}] 异常: {e}")

        # 篇间间隔（避免保存API被限流，7050错误）
        # 7050限流约需5分钟冷却，所以篇间等待300秒
        if i < total:
            wait_sec = 300  # 5分钟
            print(f"\n  >> 等待 {wait_sec}秒 后继续下一篇（避免7050限流）...", flush=True)
            blog(f"[{i}/{total}] 等待 {wait_sec}秒")
            time.sleep(wait_sec)

    blog(f"批量上传完成：{success}/{total} 篇成功")
    print(f"\n{'='*60}", flush=True)
    print(f"批量上传完成：{success}/{total} 篇成功", flush=True)
    print("注意：封面图未上传，需手动补充", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
