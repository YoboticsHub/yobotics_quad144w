# signaling_server.py
import asyncio   #python异步框架
import websockets  #websockets第三方库
import os
import json  #json数据库

clients = set()  #使用全局集合储存Websocket客户端
latest_offer = None  # 最近一次 Offer（原始 JSON 字符串），用于诊断/状态记录
publisher_client = None  # 当前发布端 WebSocket

FLAG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'restart.flag')
EXTERNAL_READY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'external_ready.flag')

def request_restart():
    try:
        with open(FLAG_PATH, 'w') as f:
            f.write('restart')
    except OSError as exc:
        print(f"无法写入重启信号: {exc}")

async def handler(websocket, path=None):  #兼容新旧 websockets handler 签名
    global latest_offer, publisher_client
    is_publisher = False
    clients.add(websocket)  #将新客户端连接到集合
    client_id = f"{websocket.remote_address or 'unknown'}#{id(websocket) % 10000}"
    print(f"[信令] 客户端接入: {client_id}，当前连接数={len(clients)}", flush=True)
    # 控制脚本据此启动 publisher；此时尚未有本机 publisher 连接。
    try:
        with open(EXTERNAL_READY_PATH, 'w') as ready_file:
            ready_file.write('ready')
    except OSError as exc:
        print(f"[信令] 无法写入外部客户端就绪标记: {exc}", flush=True)
    try:
        # publisher 已注册时，外部客户端接入会触发 publisher 发送新的 Offer。
        if publisher_client is not None and publisher_client is not websocket:
            try:
                await publisher_client.send(json.dumps({"type": "peer_ready"}))
                publisher_id = f"{publisher_client.remote_address or 'unknown'}#{id(publisher_client) % 10000}"
                print(f"[信令] → {publisher_id} type=peer_ready", flush=True)
            except websockets.exceptions.ConnectionClosed:
                print("[信令] publisher 在发送 peer_ready 前已断开", flush=True)
                clients.discard(publisher_client)
                publisher_client = None
                request_restart()
        async for message in websocket:  #异步监听每一条Websocket消息
            # 保留消息类型和长度，便于确认 Offer/Answer 是否走到了正确的客户端。
            try:
                data = json.loads(message)
                msg_type = data.get("type", "-")
                print(f"[信令] ← {client_id} type={msg_type} bytes={len(message)}", flush=True)
                if msg_type == "register" and data.get("role") == "publisher":
                    publisher_client = websocket
                    is_publisher = True
                    print(f"[信令] 已注册 publisher: {client_id}", flush=True)
                    # 外部 App 可能已经先接入，此时立即通知刚注册的 publisher。
                    if len(clients) > 1:
                        await websocket.send(json.dumps({"type": "peer_ready"}))
                        print(f"[信令] → {client_id} type=peer_ready", flush=True)
                    continue
                if msg_type in ("register", "peer_ready"):
                    continue
                if msg_type == "offer" and "sdp" in data:
                    latest_offer = message
                    print(f"[信令] 已更新缓存 Offer，bytes={len(message)}", flush=True)
            except (TypeError, json.JSONDecodeError) as exc:
                print(f"[信令] ← {client_id} 非 JSON 消息: {exc}; raw={message[:200]!r}", flush=True)
                continue
            # 只转发给其他客户端（不是自己）
            for client in tuple(clients):  #将消息转发给其他客户端
                if client != websocket:
                    try:
                        await client.send(message)
                        target_id = f"{client.remote_address or 'unknown'}#{id(client) % 10000}"
                        print(f"[信令] → {target_id} type={msg_type}", flush=True)
                    except websockets.exceptions.ConnectionClosed:
                        clients.discard(client)
                        print(f"[信令] 转发目标已断开，已移出客户端集合", flush=True)
                        request_restart()
    except websockets.exceptions.ConnectionClosed:
        print(f"[信令] 客户端断开连接: {client_id}，准备重启服务", flush=True)
        request_restart()
    except Exception as exc:
        print(f"信令处理异常: {exc}")
        request_restart()
    finally:
        clients.discard(websocket)  #清理断开的连接
        if is_publisher and publisher_client is websocket:
            publisher_client = None
        if not clients:
            try:
                os.remove(EXTERNAL_READY_PATH)
            except FileNotFoundError:
                pass
        print(f"[信令] 客户端离开: {client_id}，当前连接数={len(clients)}", flush=True)

print("Signaling server running on ws://0.0.0.0:8765", flush=True)
asyncio.get_event_loop().run_until_complete(
    websockets.serve(handler, "0.0.0.0", 8765)  #启动Websokcet服务器，监听所有网络接口的8765端口
)
asyncio.get_event_loop().run_forever()  #循环运行事件，保持服务器存活
