import subprocess
import threading
import sys
import os
import time
import socket

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISHER_PATH = os.path.join(SCRIPT_DIR, 'publisher.py')
SIGNALING_PATH = os.path.join(SCRIPT_DIR, 'signaling_server.py')
EXTERNAL_READY_PATH = os.path.join(SCRIPT_DIR, 'external_ready.flag')

publisher_proc = None
signaling_proc = None
last_restart_time = 0.0


def start_signaling():
    global signaling_proc
    if signaling_proc is None or signaling_proc.poll() is not None:
        signaling_proc = subprocess.Popen([
            sys.executable, SIGNALING_PATH
        ])
        print("signaling_server.py 已启动 (PID: {})".format(signaling_proc.pid))
    else:
        print("signaling_server.py 已在运行 (PID: {})".format(signaling_proc.pid))


def wait_for_signaling(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    print("警告: signaling_server 端口 8765 未在规定时间内就绪")
    return False


def wait_for_external_app(timeout=None):
    """等待外部 App 完成 WebSocket 握手，再启动 publisher。"""
    start_time = time.monotonic()
    print("等待外部 App 连接信令服务...", flush=True)
    while timeout is None or time.monotonic() - start_time < timeout:
        if os.path.exists(EXTERNAL_READY_PATH):
            print("检测到外部 App 已连接，准备启动 publisher", flush=True)
            return True
        time.sleep(0.2)
    return False


def stop_signaling():
    global signaling_proc
    if signaling_proc is not None and signaling_proc.poll() is None:
        signaling_proc.terminate()
        signaling_proc.wait()
        print("signaling_server.py 已停止")
        signaling_proc = None
    else:
        print("signaling_server.py 未运行")


def clear_external_ready_flag():
    try:
        os.remove(EXTERNAL_READY_PATH)
    except FileNotFoundError:
        pass


def start_publisher():
    global publisher_proc
    if publisher_proc is None or publisher_proc.poll() is not None:
        publisher_proc = subprocess.Popen([
            sys.executable, PUBLISHER_PATH
        ])
        print("publisher.py 已启动 (PID: {})".format(publisher_proc.pid))
    else:
        print("publisher.py 已在运行 (PID: {})".format(publisher_proc.pid))


def stop_publisher():
    global publisher_proc
    if publisher_proc is not None and publisher_proc.poll() is None:
        publisher_proc.terminate()
        publisher_proc.wait()
        print("publisher.py 已停止")
        publisher_proc = None
    else:
        print("publisher.py 未运行")


def listen_keys():
    print("按 s 启动，q 停止，e 退出控制脚本")
    while True:
        key = input().strip().lower()
        if key == 's':
            start_publisher()
        elif key == 'q':
            stop_publisher()
        elif key == 'e':
            stop_publisher()
            stop_signaling()
            print("退出控制脚本")
            break
        else:
            print("无效按键，请按 s(启动), q(停止), e(退出)")


def monitor_restart_flag():
    flag_path = os.path.join(SCRIPT_DIR, 'restart.flag')
    global publisher_proc, signaling_proc, last_restart_time

    while True:
        # 检测 restart.flag 文件
        if os.path.exists(flag_path):
            now = time.monotonic()
            if now - last_restart_time < 3.0:
                time.sleep(0.5)
                continue
            last_restart_time = now
            print("检测到重启信号，正在重启 signaling_server 和 publisher...")
            stop_publisher()
            stop_signaling()
            clear_external_ready_flag()
            try:
                os.remove(flag_path)
            except FileNotFoundError:
                pass
            time.sleep(1)
            start_signaling()
            wait_for_signaling()
            wait_for_external_app()
            start_publisher()

        # 检测 signaling_server 是否崩溃
        if signaling_proc is not None and signaling_proc.poll() is not None:
            print("检测到 signaling_server 崩溃，正在重启...")
            stop_signaling()
            time.sleep(1)
            start_signaling()

        # 检测 publisher 是否崩溃
        if publisher_proc is not None and publisher_proc.poll() is not None:
            print("检测到 publisher 崩溃，正在重启...")
            stop_publisher()
            time.sleep(1)
            start_publisher()

        time.sleep(1)



if __name__ == '__main__':

    # 1. 启动核心服务

    clear_external_ready_flag()
    start_signaling()
    wait_for_signaling()
    wait_for_external_app()
    start_publisher()



    # 2. 启动后台监控线程（如果这个线程是用来监控子进程崩溃并重启的，保留它）

    restart_thread = threading.Thread(target=monitor_restart_flag, daemon=True)

    restart_thread.start()



    # 3. 【修改点】不再调用 listen_keys()

    # 改为无限循环或等待，保持主进程存活，让 systemd 认为服务正在运行

    try:

        print(">>> WebRTC 服务已在后台启动 (由 systemd 托管)")

        while True:

            time.sleep(1) # 简单的死循环等待，避免主线程退出

    except KeyboardInterrupt:

        print("收到退出信号...")

    finally:

        # 4. 清理资源

        stop_publisher()

        stop_signaling()

        print("服务已停止")
