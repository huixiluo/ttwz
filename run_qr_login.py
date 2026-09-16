# -*- coding: utf-8 -*-
"""头条扫码登录（无浏览器依赖版）：生成二维码→轮询→完成登录→保存cookie"""
import time
import toutiao_login as tl

session = None
import requests
session = requests.Session()
session.headers.update({"User-Agent": tl.UA})

print("[1] 获取登录二维码...")
token = tl.get_qrcode(session)
print("二维码已生成: /workspace/toutiao_qr.png")

print("[2] 等待扫码（最长5分钟，过期自动刷新）...")
max_wait = 300
start = time.time()
while time.time() - start < max_wait:
    time.sleep(2)
    status, extra = tl.check_login_status(session, token)
    elapsed = int(time.time() - start)
    if status == 0:
        if elapsed % 10 == 0:
            print(f"  [{elapsed}s] 等待扫码...")
    elif status == 1:
        print(f"  [{elapsed}s] 已扫码，等待手机确认...")
    elif status == 2:
        print(f"  [{elapsed}s] 登录成功！")
        print("[3] 完成登录跳转...")
        tl.complete_login(session, extra, token)
        ok = tl.save_cookies(session)
        print("LOGIN_DONE" if ok else "LOGIN_NO_AUTH_COOKIE")
        break
    elif status == 3:
        print(f"  [{elapsed}s] 二维码过期，刷新...")
        token = tl.get_qrcode(session)
        start = time.time()
else:
    print("LOGIN_TIMEOUT")
