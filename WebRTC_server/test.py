# publisher.py

import os
import asyncio
import json
import signal
import sys
import cv2
import numpy as np
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    VideoStreamTrack,
    RTCRtpSender
)
from av import VideoFrame
import websockets
import threading


# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'lcm-types', 'python'))

LCM_AVAILABLE = False
try:
    import lcm
    from sport_client_cmd_t import sport_client_cmd_t
    from sport_client_state_t import sport_client_state_t

    LCM_AVAILABLE = True
except ImportError as e:
    print(f"警告: LCM 模块导入失败: {e}")
    LCM_AVAILABLE = False

# LCM 通道名称（默认值，将从配置文件读取）
DEFAULT_ROBOT_CONTROL_CHANNEL = "QUAD_ROBOT_CONTROL_Y20W"
DEFAULT_ROBOT_STATE_CHANNEL = "QUAD_ROBOT_STATE_Y20W"


# ==========================================
# 全局变量定义
# ==========================================
source_track = None
pc = None
websocket = None
global_datachannel = None
p2p_connected = False
offer_task = None
messages = []

# 新增：控制主循环的标志
running = True       # 控制整个程序是否运行
session_task = None  # 用于存储当前的 run_publisher 任务

class LCMCommunicator:
    def __init__(self, loop, lcm_url="", control_channel=DEFAULT_ROBOT_CONTROL_CHANNEL,
                 state_channel=DEFAULT_ROBOT_STATE_CHANNEL):
        self.loop = loop
        self.lcm_url = lcm_url
        self.control_channel = control_channel
        self.state_channel = state_channel
        self.lcm = None
        self.thread = None
        self._running = False
        self.on_state_callback = None  # 用于接收解析后的 JSON 状态

        try:
            self.lcm = lcm.LCM(self.lcm_url if self.lcm_url else None)
            print(f"[LCM] 初始化成功 (URL: {self.lcm_url or 'default'})")
        except Exception as e:
            print(f"[LCM] 初始化失败: {e}")
            self.lcm = None

    def _state_handler(self, channel, data):
        """LCM 回调：处理 sport_client_state_t"""
        if channel != self.state_channel:
            return
        try:
            msg = sport_client_state_t.decode(data)
            json_msg = {
                "code": int(0),
                "power": [round(float(msg.power[0]), 2), round(float(msg.power[1]), 2)] if len(msg.power) >= 2 else [0.0, 0.0],
                "rpy": [round(float(x), 2) for x in msg.rpy[:3]] if len(msg.rpy) >= 3 else [0.0, 0.0, 0.0],
                "v": [round(float(msg.v), 2)],
                "h": [round(float(msg.h), 2)],
                "state": int(msg.state),
                "fault": int(msg.fault),
                "env": [round(float(x), 2) for x in msg.env[:3]] if len(msg.env) >= 3 else [0.0, 0.0, 0.0]
            } 
            # print(json.dumps(json_msg, indent=4, ensure_ascii=False))

            if self.on_state_callback:
                # 线程安全地调用 asyncio 回调
                self.loop.call_soon_threadsafe(self.on_state_callback, json_msg)
        except Exception as e:
            print(f"[LCM State Handler] 解码失败: {e}")

    def _lcm_run(self):
        """LCM 监听线程主循环"""
        if not self.lcm:
            return
        self.lcm.subscribe(self.state_channel, self._state_handler)
        print(f"[LCM] 开始监听状态通道: {self.state_channel}")
        while self._running:
            self.lcm.handle_timeout(100)  # 100ms 超时

    def start(self):
        """启动 LCM 监听线程"""
        if not self.lcm:
            return
        self._running = True
        self.thread = threading.Thread(target=self._lcm_run, daemon=True)
        self.thread.start()

    def stop(self):
        """停止 LCM 监听"""
        self._running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def send_command(self, json_data):
        """从 JSON 发送 LCM 命令"""
        if not self.lcm:
            print("[LCM] 未初始化，无法发送命令")
            return False
        try:

            cmd = sport_client_cmd_t()
            cmd.api = int(json_data.get("mode", 0))
            cmd.velocity = [float(x) for x in json_data.get("v", [0.0, 0.0, 0.0])][:3]
            cmd.euler_angles = [float(x) for x in json_data.get("rpy", [0.0, 0.0, 0.0])][:3]
            cmd.body_height = 0.0
            cmd.rc_enable = 0
            cmd.step_height = 0.0

            self.lcm.publish(self.control_channel, cmd.encode())
            print(f"[LCM] 已发布命令到 {self.control_channel}")
            return True
        except Exception as e:
            print(f"[LCM] 命令发送失败: {e}")
            return False
        
# ========================
# 视频轨道：普通 USB 摄像头（如 /dev/video4）
# ========================
class USBCameraTrack(VideoStreamTrack):
    """自定义视频轨道类，从 USB 摄像头读取帧并提供给 WebRTC"""
    kind = "video"  # 必须指定为 "video" 或 "audio"

    def __init__(self, device_index=4, width=1920, height=1080, fps=30):
        super().__init__()  # 调用父类构造函数
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = 0  # 用于生成 PTS（Presentation Timestamp） 

        # 打开摄像头设备（Linux 下通常是 /dev/videoX）
        self.cap = cv2.VideoCapture(self.device_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 /dev/video{device_index}")

        # 设置摄像头格式为 MJPG（Motion JPEG），可显著提升性能（减少 CPU 解码负担）
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

        # 读取几帧“预热”摄像头，避免初始黑屏或延迟
        for _ in range(5):
            self.cap.read()

        print(f"🎥 USB 摄像头 /dev/video{device_index} 启动成功 ({width}x{height} @ {fps}fps)")

    async def recv(self):
        """
        异步方法：被 aiortc 调用以获取下一帧视频。
        必须返回一个 VideoFrame 对象。
        """
        loop = asyncio.get_event_loop()
        try:
            # 在线程池中执行阻塞的 cap.read()，避免阻塞事件循环
            ret, frame_bgr = await loop.run_in_executor(None, self.cap.read)
            if not ret or frame_bgr is None:
                # 如果读取失败，等待一帧时间后重试
                await asyncio.sleep(1 / self.fps)
                return await self.recv()

            self.frame_count += 1
            # OpenCV 默认是 BGR，需转为 RGB 供 WebRTC 使用
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            # 如果分辨率不匹配（某些摄像头可能忽略设置），强制调整
            if frame_rgb.shape[0] != self.height or frame_rgb.shape[1] != self.width:
                frame_rgb = cv2.resize(frame_rgb, (self.width, self.height))

            # 将 NumPy 数组转换为 aiortc 的 VideoFrame
            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            # 设置时间基准（time_base）为 1/fps，用于计算 PTS
            video_frame.time_base = f"1/{self.fps}"
            # 计算 PTS（单位：90kHz 时钟，WebRTC 标准）
            pts = self.frame_count * (9000 // self.fps)  # 注意：9000 是 90kHz / 10，简化计算
            video_frame.pts = pts
            video_frame.dts = pts  # DTS 通常等于 PTS（无 B 帧）

            return video_frame

        except Exception as e:
            print(f"[Publisher] recv 错误: {e}")
            await asyncio.sleep(1 / self.fps)
            return await self.recv()  # 递归重试

    def stop(self):
        """释放摄像头资源""" 
        super().stop()
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
            print("🛑 USB 摄像头已释放")


# ==========================================
# 信令与辅助函数 (保持逻辑不变)
# ==========================================
async def send_signaling(msg):
    if websocket and websocket.open:
        await websocket.send(json.dumps(msg))
    else:
        print("[信令] WebSocket 未连接，无法发送信令")

async def create_and_send_offer():
    global pc
    try:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await send_signaling({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
        print("[WebRTC] 已发送 Offer")
    except Exception as e:
        print(f"[WebRTC] 发送 Offer 失败: {e}")

async def offer_sender():
    global pc, p2p_connected
    while True:
        if pc and not p2p_connected and pc.connectionState in ["new", "failed", "closed"]:
            await create_and_send_offer()
        await asyncio.sleep(2)

async def handle_signaling_as_offerer():
    global pc, p2p_connected, websocket
    try:
        # 原来的代码是: async for raw in websocket:
        async for raw in websocket:
            print(f"[DEBUG] 收到原始消息: {raw}") # <--- 加这一行调试，看看到底收到了什么
            
            try:
                data = json.loads(raw)
                # 确保是字典类型
                if not isinstance(data, dict):
                    continue
                    
                if "sdp" in data and data["type"] == "answer":
                    sdp = RTCSessionDescription(sdp=data["sdp"], type="answer")
                    await pc.setRemoteDescription(sdp)
                    p2p_connected = True
                    print("[WebRTC] ✅ 收到 Answer，P2P 已建立")
                    
                elif "candidate" in data:
                    candidate_str = data["candidate"]
                    # 检查是否是有效的 Candidate 字符串
                    if isinstance(candidate_str, str) and candidate_str.startswith("candidate:"):
                        # 关键修改：将字符串包装成包含 'candidate' 键的字典
                        candidate_obj = {"candidate": candidate_str}
                        try:
                            await pc.addIceCandidate(candidate_obj)
                            print(f"[ICE] 成功添加 Candidate")
                        except Exception as e:
                            print(f"[ICE] 添加 Candidate 失败: {e}")
                    else:
                        print(f"[ICE] 无效的 Candidate 格式，已忽略: {candidate_str}")
                                    
            except json.JSONDecodeError:
                # 如果不是 JSON（比如是纯文本心跳包 "ping"），忽略
                print("[信令] 收到非 JSON 消息（可能是心跳包），已忽略")
                continue
            except Exception as e:
                print(f"[信令-Offerer] 处理消息错误: {e}")
                # print traceback
                import traceback
                traceback.print_exc()
                
    except websockets.exceptions.ConnectionClosed:
        print("[信令] WebSocket 连接关闭")
    except Exception as e:
        print(f"[信令] 发生异常: {e}")
# ==========================================
# 核心修改：按键控制逻辑
# ==========================================
async def input_listener():
    """监听键盘输入"""
    global running, session_task
    
    print("\n" + "="*50)
    print("🚀 发布端控制台 (按以下键执行操作)")
    print("   1 -> 开始推流 (建立连接)")
    print("   2 -> 停止推流 (断开连接)")
    print("   q -> 退出程序")
    print("="*50)
    
    while running:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(None, input, "等待指令 (1/2/q): ")
            cmd = cmd.strip().lower()
            
            if cmd == '1':
                # 如果已经有任务在运行，先取消它
                if session_task and not session_task.done():
                    print("[控制] 检测到旧连接，正在强制停止...")
                    session_task.cancel()
                    try:
                        await session_task
                    except asyncio.CancelledError:
                        pass
                
                # 创建新的连接任务
                print("[控制] 用户指令：启动连接")
                session_task = asyncio.create_task(run_publisher())
                
            elif cmd == '2':
                if session_task and not session_task.done():
                    print("[控制] 用户指令：强制停止连接")
                    session_task.cancel()
                else:
                    print("[控制] 当前无活动连接")
                    
            elif cmd == 'q':
                print("[控制] 用户指令：退出程序")
                running = False
                if session_task:
                    session_task.cancel()
                break
                
            else:
                print("无效指令，请输入 1, 2, 或 q")
                
        except Exception as e:
            if running:
                print(f"输入监听错误: {e}")
            await asyncio.sleep(0.1)

# ==========================================
# 主运行函数 (重构版)
# ==========================================
async def run_publisher():
    """
    此函数现在是一个“单次连接”任务。
    连接断开后会直接退出，由 input_listener 控制是否重启。
    """
    global websocket, pc, global_datachannel, p2p_connected, offer_task
    
    # 本地资源管理
    _local_pc = None
    _local_websocket = None
    _local_lcm = None
    
    try:
        # --- 1. 初始化 LCM ---
        lcm_comm = None
        try:
            lcm_comm = LCMCommunicator(
                loop=asyncio.get_event_loop(),
                lcm_url="udpm://239.255.76.67:7667?ttl=255",
                control_channel=DEFAULT_ROBOT_CONTROL_CHANNEL,
                state_channel=DEFAULT_ROBOT_STATE_CHANNEL
            )
            lcm_comm.start()
            _local_lcm = lcm_comm
            print("[LCM] 初始化完成")
        except Exception as e:
            print(f"[LCM] 初始化失败: {e}")

        # --- 2. WebSocket 连接 ---
        _local_websocket = await websockets.connect("ws://localhost:8765")
        websocket = _local_websocket
        print("[信令] 已连接到 ws://localhost:87675")

        # --- 3. 创建 PeerConnection ---
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        _local_pc = pc
        
        # --- 4. 设置事件监听器 ---
        # DataChannel: Chat
        global_datachannel = pc.createDataChannel("chat")
        
        @global_datachannel.on("open")
        def on_open():
            print("[DataChannel] 通道已打开")

        @global_datachannel.on("message")
        def on_message(message):
            print(f"[DataChannel] ← 收到: {message}")
            messages.append(f"← {message}")
            
            # LCM 发送逻辑
            if _local_lcm:
                try:
                    data = json.loads(message)
                    _local_lcm.send_command(data)
                except json.JSONDecodeError as e:
                    print(f"[DataChannel] JSON 解析失败: {e}")

        # WebRTC 状态监听
        @pc.on("connectionstatechange")
        async def on_connection_state_change():
            global p2p_connected
            state = pc.connectionState
            print(f"[WebRTC] 连接状态: {state}")
            if state == "connected":
                p2p_connected = True
            elif state in ["failed", "closed", "disconnected"]:
                p2p_connected = False

        # --- 5. 添加轨道与编解码器设置 (保留你的 H264 逻辑) ---
        if source_track is None:
            raise Exception("摄像头未初始化")
        pc.addTrack(source_track)
        
        transceiver = pc.getTransceivers()[0]
        codecs = RTCRtpSender.getCapabilities("video").codecs
        h264_codecs = [c for c in codecs if c.mimeType == "video/H264"]
        
        if h264_codecs:
            transceiver.setCodecPreferences(h264_codecs)
            print("[WebRTC] 💾 已设置使用 H264 编码 (低延迟)")
        else:
            vp8_codecs = [c for c in codecs if c.mimeType == "video/VP8"]
            if vp8_codecs:
                transceiver.setCodecPreferences(vp8_codecs)
                print("[WebRTC] ⚠️ H264 不可用，回退到 VP8")
            else:
                print("[WebRTC] ❌ 错误：无可用视频编码器")

        # --- 6. 启动后台任务 ---
        offer_task = asyncio.create_task(offer_sender())
        
        # --- 7. 主信令循环 ---
        await create_and_send_offer()
        await handle_signaling_as_offerer()

    except asyncio.CancelledError:
        print("[控制] 连接任务被用户取消")
        raise
    except Exception as e:
        print(f"[Publisher] 连接异常: {e}")
    finally:
        # --- 8. 资源清理 ---
        print("[清理] 正在释放资源...")
        
        if offer_task:
            offer_task.cancel()
            try:
                await offer_task
            except asyncio.CancelledError:
                pass
        
        if _local_pc:
            await _local_pc.close()
        
        if _local_lcm:
            _local_lcm.stop()
        
        if _local_websocket:
            await _local_websocket.close()
            
        print("[清理] 资源释放完成")

# ==========================================
# 程序入口
# ==========================================
async def main():
    global source_track
    
    # 1. 初始化摄像头 (只做一次)
    try:
        source_track = USBCameraTrack(device_index=4, width=1280, height=720, fps=30)
        print("[初始化] 摄像头准备就绪")
    except Exception as e:
        print(f"[错误] 无法初始化摄像头: {e}")
        return

    # 2. 启动输入监听
    await input_listener()

if __name__ == "__main__":
    # 注册信号处理器 (Ctrl+C)
    def signal_handler(sig, frame):
        global running
        print("\n[!] 正在关闭...")
        running = False
        
    signal.signal(signal.SIGINT, signal_handler)
    
    # 启动主程序
    asyncio.run(main())
