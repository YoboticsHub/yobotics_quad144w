# publisher.py

# 导入所需模块
import os
import asyncio                 # 异步 I/O 框架
import json                    # JSON 编解码
import signal                  # 处理系统信号（如 Ctrl+C）
import sys                     # 系统相关功能
import cv2                     # OpenCV，用于摄像头操作
import numpy as np             # 数值计算（虽然这里未直接使用，但常配合 OpenCV）
from aiortc import (         # WebRTC 实现库
    RTCPeerConnection,         # WebRTC 对等连接对象
    RTCSessionDescription,     # SDP 会话描述（Offer/Answer）
    RTCConfiguration,          # ICE 配置（如 STUN/TURN 服务器）
    VideoStreamTrack,          # 自定义视频轨道基类
    RTCRtpSender               # RTP 发送器，用于编解码器控制
)
from av import VideoFrame      # PyAV 库，用于处理音视频帧
import websockets              # WebSocket 客户端/服务端库
from aiortc.sdp import candidate_from_sdp
from aiortc import RTCIceCandidate
import threading
import time
from fractions import Fraction
from urllib.parse import urlsplit, urlunsplit

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'lcm-types', 'python'))

# ========================
# 配置文件加载
# ========================
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
config = {
    'use_camera': True,
    'camera': {'source_type': 'usb', 'device_index': 4, 'rtsp_url': '', 'width': 1920, 'height': 1080, 'fps': 30},
    'lcm': {'url': 'udpm://239.255.76.67:7667?ttl=255', 'control_channel': 'QUAD_ROBOT_CONTROL_Y20W', 'state_channel': 'QUAD_ROBOT_STATE_Y20W'},
    'signaling': {'server': 'ws://localhost:8765'},
    'webrtc': {
        'low_latency': True,
        'max_fps': 20,
        'min_bitrate_kbps': 600,
        'start_bitrate_kbps': 1500,
        'max_bitrate_kbps': 2500
    }
}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[配置] 已加载配置文件: {CONFIG_FILE}")
    except Exception as e:
        print(f"[配置] 加载配置文件失败: {e}，使用默认配置")
else:
    print(f"[配置] 配置文件不存在: {CONFIG_FILE}，使用默认配置")

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
            # print(msg.state)
            # 发送消息
            # print(json_msg)

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
            cmd.body_height = float(json_data.get("h", [0.0])[0])
            variable = [int(x) for x in json_data.get("variable", [0, 0, 0])][:3]
            cmd.variable = variable + [0] * (3 - len(variable))
            cmd.rc_enable = 1
            cmd.step_height = 0.0

            self.lcm.publish(self.control_channel, cmd.encode())
            # print(f"[LCM] 已发布命令到 {self.control_channel}")
            return True
        except Exception as e:
            print(f"[LCM] 命令发送失败: {e}")
            return False
        
# ========================
# 视频轨道：虚拟轨道（当禁用相机时使用）
# ========================
class DummyVideoTrack(VideoStreamTrack):
    """虚拟视频轨道，生成黑屏或测试画面"""
    kind = "video"

    def __init__(self, width=1920, height=1080, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = 0
        print(f"📺 虚拟视频轨道已创建 ({width}x{height} @ {fps}fps)")

    async def recv(self):
        """返回一个黑屏帧"""
        # 创建黑屏（RGB 图像）
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # 为黑屏添加文字提示（第一帧）
        if self.frame_count == 0:
            cv2.putText(frame, "Camera Disabled", (self.width // 2 - 150, self.height // 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
        
        self.frame_count += 1
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.time_base = Fraction(1, 90000)
        pts = self.frame_count * max(1, int(90000 / self.fps))
        video_frame.pts = pts
        video_frame.dts = pts
        
        # 控制帧率
        await asyncio.sleep(1 / self.fps)
        return video_frame

    def stop(self):
        """停止虚拟轨道"""
        super().stop()
        print("📺 虚拟视频轨道已停止")

        
# ========================
# 视频轨道：OpenCV 视频源（USB 摄像头 / RTSP）
# ========================
class OpenCVVideoTrack(VideoStreamTrack):
    """自定义视频轨道类，从 OpenCV 视频源读取帧并提供给 WebRTC"""
    kind = "video"  # 必须指定为 "video" 或 "audio"

    def __init__(self, source, source_label, width=1920, height=1080, fps=30, low_latency=False,
                 configure_usb=False, require_initial_frame=False):
        super().__init__()  # 调用父类构造函数
        self.source = source
        self.source_label = source_label
        self.width = width
        self.height = height
        self.fps = fps
        self.low_latency = low_latency
        self.frame_count = 0  # 用于生成 PTS（Presentation Timestamp）

        # 打开 OpenCV 视频源（Linux 摄像头设备号或 RTSP URL）
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频源 {self.source_label}")

        if configure_usb:
            # USB 摄像头设置 MJPG 可显著提升性能；RTSP 不强制设置，避免影响网络流解码。
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)
        if hasattr(cv2, 'CAP_PROP_BUFFERSIZE'):
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame_lock = threading.Lock()
        self._latest_frame = None

        # 读取几帧“预热”视频源，避免初始黑屏或延迟；RTSP 读不到首帧时直接触发回退。
        warmup_attempts = 30 if require_initial_frame else 5
        for _ in range(warmup_attempts):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self._latest_frame = frame
                break
            if require_initial_frame:
                time.sleep(0.05)

        if require_initial_frame and self._latest_frame is None:
            self.cap.release()
            raise RuntimeError(f"视频源 {self.source_label} 已打开但无法读取首帧")

        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        latency_tag = '低时延模式' if self.low_latency else '普通模式'
        print(f"🎥 视频源 {self.source_label} 启动成功 ({width}x{height} @ {fps}fps, {latency_tag})")

    def _reader_loop(self):
        """后台线程持续读取摄像头，仅保留最新一帧，避免缓冲堆积导致高延迟。"""
        while self._running:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.002)
                continue
            with self._frame_lock:
                self._latest_frame = frame

    async def recv(self):
        """
        异步方法：被 aiortc 调用以获取下一帧视频。
        必须返回一个 VideoFrame 对象。
        """
        while True:
            try:
                frame_bgr = None
                with self._frame_lock:
                    if self._latest_frame is not None:
                        frame_bgr = self._latest_frame.copy()

                if frame_bgr is None:
                    await asyncio.sleep(1 / max(self.fps, 1))
                    continue

                self.frame_count += 1
                # OpenCV 默认是 BGR，需转为 RGB 供 WebRTC 使用
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                # 如果分辨率不匹配（某些摄像头可能忽略设置），强制调整
                if frame_rgb.shape[0] != self.height or frame_rgb.shape[1] != self.width:
                    frame_rgb = cv2.resize(frame_rgb, (self.width, self.height))

                # 将 NumPy 数组转换为 aiortc 的 VideoFrame
                video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
                # 设置时间基准（time_base）为 1/fps，用于计算 PTS
                video_frame.time_base = Fraction(1, 90000)
                # 计算 PTS（单位：90kHz 时钟，WebRTC 标准）
                pts = self.frame_count * max(1, int(90000 / self.fps))
                video_frame.pts = pts
                video_frame.dts = pts  # DTS 通常等于 PTS（无 B 帧）

                return video_frame

            except Exception as e:
                print(f"[Publisher] recv 错误: {e}")
                await asyncio.sleep(1 / max(self.fps, 1))

    def stop(self):
        """释放视频源资源"""
        super().stop()
        self._running = False
        if hasattr(self, '_reader_thread') and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
            print(f"🛑 视频源 {self.source_label} 已释放")


def sanitize_rtsp_url(rtsp_url):
    """隐藏 RTSP URL 中的密码，避免日志泄露凭据。"""
    try:
        parts = urlsplit(rtsp_url)
        if not parts.username:
            return rtsp_url
        hostname = parts.hostname or ''
        port = f":{parts.port}" if parts.port else ''
        username = parts.username
        netloc = f"{username}:***@{hostname}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "rtsp://***"


class USBCameraTrack(OpenCVVideoTrack):
    """USB 摄像头视频轨道（如 /dev/video4）"""

    def __init__(self, device_index=4, width=1920, height=1080, fps=30, low_latency=False):
        self.device_index = int(device_index)
        super().__init__(
            source=self.device_index,
            source_label=f"USB 摄像头 /dev/video{self.device_index}",
            width=width,
            height=height,
            fps=fps,
            low_latency=low_latency,
            configure_usb=True
        )


class RTSPCameraTrack(OpenCVVideoTrack):
    """RTSP 网络视频流轨道"""

    def __init__(self, rtsp_url, width=1920, height=1080, fps=30, low_latency=False):
        if not rtsp_url:
            raise ValueError("camera.rtsp_url 为空")
        self.rtsp_url = rtsp_url
        self.safe_rtsp_url = sanitize_rtsp_url(rtsp_url)
        super().__init__(
            source=self.rtsp_url,
            source_label=f"RTSP 数据流 {self.safe_rtsp_url}",
            width=width,
            height=height,
            fps=fps,
            low_latency=low_latency,
            configure_usb=False,
            require_initial_frame=True
        )


# ========================
# 全局状态变量（用于跨协程共享）
# ========================
source_track = None           # 摄像头视频轨道实例
pc = None                     # RTCPeerConnection 实例
websocket = None              # WebSocket 连接
messages = []                 # 存储收到的消息（用于退出时打印）
global_datachannel = None     # DataChannel 实例
p2p_connected = False         # 标记 P2P 连接是否已建立
offer_task = None             # 定时发送 Offer 的后台任务句柄
bitrate_task = None           # 实时打印上行速率的后台任务句柄
webrtc_latency_profile = None  # 低时延参数
restart_requested = False      # 避免多个协程重复触发重启
offer_in_flight = False        # 防止重复发送 Offer
peer_ready_event = None        # 外部客户端接入后由信令服务触发

def request_restart(reason):
    global restart_requested
    if restart_requested:
        return
    restart_requested = True
    flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'restart.flag')
    try:
        with open(flag_path, 'w') as f:
            f.write('restart')
        print(f"[重启] 已请求服务重启: {reason}")
    except OSError as exc:
        print(f"[重启] 写入 restart.flag 失败: {exc}")


# ========================
# 终端输入监听协程：允许用户从终端发送消息到订阅端
# ========================
async def stdin_sender():
    global global_datachannel
    loop = asyncio.get_event_loop()
    print("\n[提示] 现在可以在终端输入消息，按回车发送给订阅端（输入 'quit' 退出输入模式）\n")
    while True:
        try:
            # 在线程中阻塞等待用户输入（避免阻塞事件循环）
            msg = await loop.run_in_executor(None, input, ">>> ")
            if msg.strip().lower() == "quit":
                print("退出终端输入模式。")
                break
            # 检查 DataChannel 是否可用
            if global_datachannel and global_datachannel.readyState == "open":
                global_datachannel.send(msg)
                print(f"→ 已发送: {msg}")
            else:
                print("⚠️ DataChannel 未就绪或已关闭，无法发送")
        except EOFError:
            # 用户可能通过 Ctrl+D 结束输入
            break
        except Exception as e:
            print(f"输入错误: {e}")
            break


# ========================
# 信令通信函数
# ========================
async def send_signaling(msg):
    """通过 WebSocket 发送信令消息（SDP 或 ICE candidate）"""
    # websockets 不同版本分别提供 open/closed 属性，统一兼容处理。
    is_open = websocket is not None and not bool(getattr(websocket, "closed", False))
    if websocket is not None and hasattr(websocket, "open"):
        is_open = bool(websocket.open)
    if is_open:
        payload = json.dumps(msg)
        await websocket.send(payload)
        print(f"[信令] → type={msg.get('type', '-')} bytes={len(payload)}", flush=True)
    else:
        print("[信令] WebSocket 未连接，无法发送信令")


def build_webrtc_latency_profile():
    """根据相机配置生成低时延参数。"""
    camera_cfg = config.get('camera', {})
    webrtc_cfg = config.get('webrtc', {})

    width = int(camera_cfg.get('width', 1920))
    height = int(camera_cfg.get('height', 1080))
    cam_fps = int(camera_cfg.get('fps', 30))
    pixels = width * height

    low_latency = bool(webrtc_cfg.get('low_latency', True))
    auto_fps = 20 if pixels >= 1920 * 1080 else 30

    profile = {
        'enabled': low_latency,
        'max_fps': int(webrtc_cfg.get('max_fps', min(cam_fps, auto_fps))),
        'min_bitrate_kbps': int(webrtc_cfg.get('min_bitrate_kbps', 600)),
        'start_bitrate_kbps': int(webrtc_cfg.get('start_bitrate_kbps', 1500)),
        'max_bitrate_kbps': int(webrtc_cfg.get('max_bitrate_kbps', 2500))
    }

    if profile['max_fps'] <= 0:
        profile['max_fps'] = max(1, cam_fps)

    return profile


def tune_offer_sdp_for_low_latency(sdp, profile):
    """对 Offer SDP 注入低时延参数（码率/帧率）。"""
    if not profile or not profile.get('enabled'):
        return sdp

    lines = sdp.split("\r\n")

    video_payloads = []
    for line in lines:
        if line.startswith("m=video "):
            parts = line.split()
            video_payloads = parts[3:]
            break

    if not video_payloads:
        return sdp

    payload_set = set(video_payloads)
    min_br = int(profile.get('min_bitrate_kbps', 600))
    start_br = int(profile.get('start_bitrate_kbps', 1500))
    max_br = int(profile.get('max_bitrate_kbps', 2500))
    max_fps = int(profile.get('max_fps', 20))

    with_bandwidth = []
    inserted_bandwidth = False
    for line in lines:
        with_bandwidth.append(line)
        if line.startswith("m=video ") and not inserted_bandwidth:
            with_bandwidth.append(f"b=AS:{max_br}")
            inserted_bandwidth = True

    tuned = []
    for line in with_bandwidth:
        if line.startswith("a=fmtp:"):
            head, tail = (line.split(" ", 1) + [""])[:2]
            payload = head.split(":", 1)[1]
            if payload in payload_set and "apt=" not in tail:
                params = [p.strip() for p in tail.split(";") if p.strip()]
                keys = {p.split("=", 1)[0].strip() for p in params if "=" in p}
                if "x-google-min-bitrate" not in keys:
                    params.append(f"x-google-min-bitrate={min_br}")
                if "x-google-start-bitrate" not in keys:
                    params.append(f"x-google-start-bitrate={start_br}")
                if "x-google-max-bitrate" not in keys:
                    params.append(f"x-google-max-bitrate={max_br}")
                if "max-fr" not in keys:
                    params.append(f"max-fr={max_fps}")
                line = head + " " + ";".join(params)
        tuned.append(line)

    return "\r\n".join(tuned)


async def create_and_send_offer():
    """创建本地 Offer 并通过信令通道发送"""
    global pc, webrtc_latency_profile, offer_in_flight
    if offer_in_flight or not pc or pc.connectionState in ("closed", "failed"):
        return False
    if pc.signalingState != "stable":
        return False
    offer_in_flight = True
    try:
        offer = await pc.createOffer()                # 创建 Offer
        tuned_sdp = tune_offer_sdp_for_low_latency(offer.sdp, webrtc_latency_profile)
        offer = RTCSessionDescription(sdp=tuned_sdp, type=offer.type)
        await pc.setLocalDescription(offer)           # 设置本地描述
        await send_signaling({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
        print("[WebRTC] 已发送 Offer")
        return True
    except Exception as e:
        print(f"[WebRTC] 发送 Offer 失败: {e}")
        # 检测到 RTCPeerConnection is closed 时，写入 restart.flag 文件
        if 'RTCPeerConnection is closed' in str(e):
            request_restart(str(e))
        return False
    finally:
        if pc and pc.signalingState == "stable":
            offer_in_flight = False


async def offer_sender():
    """
    后台任务：每 2 秒发送一次 Offer，直到 P2P 连接建立。
    这是一种“轮询式”信令策略，适用于简单场景（如本地测试）。
    """
    global p2p_connected
    while True:
        if not p2p_connected and pc and pc.connectionState not in ("closed", "failed"):
            await create_and_send_offer()
        await asyncio.sleep(2)


async def monitor_upload_kbps(interval=1.0):
    """
    周期性读取 WebRTC 发送统计并打印上行速率（kb/s）。
    计算方式：kb/s = (ΔbytesSent * 8) / Δt / 1000
    """
    global pc
    last_total_bytes = None
    last_time = None

    while True:
        try:
            if not pc:
                await asyncio.sleep(interval)
                continue

            stats = await pc.getStats()
            total_bytes = 0

            for stat in stats.values():
                if getattr(stat, "type", "") != "outbound-rtp":
                    continue
                kind = getattr(stat, "kind", None)
                if kind and kind != "video":
                    continue
                bytes_sent = getattr(stat, "bytesSent", None)
                if bytes_sent is not None:
                    total_bytes += int(bytes_sent)

            now = asyncio.get_event_loop().time()
            if last_total_bytes is not None and last_time is not None and now > last_time:
                delta_bytes = total_bytes - last_total_bytes
                delta_t = now - last_time
                if delta_bytes >= 0:
                    kbps = (delta_bytes * 8.0) / delta_t / 1000.0
                    # print(f"[WebRTC] ↑ 上传速率: {kbps:.1f} kb/s")

            last_total_bytes = total_bytes
            last_time = now
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WebRTC] 统计上传速率失败: {e}")
            await asyncio.sleep(interval)


async def handle_signaling_as_offerer():
    """
    作为 Offerer（发布端），只处理来自订阅端的 Answer 和 ICE candidates。
    """
    global pc, p2p_connected, offer_in_flight, peer_ready_event
    # 持续监听 WebSocket 消息
    try:
      async for raw in websocket:
        try:
            print(f"[信令] ← 收到原始消息 bytes={len(raw)}", flush=True)
            data = json.loads(raw)
            if data.get("type") == "peer_ready":
                if peer_ready_event:
                    peer_ready_event.set()
                print("[信令] ✅ 外部客户端已接入，可以发送 Offer", flush=True)
            elif "sdp" in data and data["type"] == "answer":
                if not pc or pc.signalingState != "have-local-offer":
                    current_state = pc.signalingState if pc else "无 PeerConnection"
                    print(f"[信令] 忽略重复或过期 Answer，当前 signalingState={current_state}", flush=True)
                    continue
                # 收到 Answer，设置远程描述
                sdp = RTCSessionDescription(sdp=data["sdp"], type="answer")
                await pc.setRemoteDescription(sdp)
                p2p_connected = True
                offer_in_flight = False
                print(f"[WebRTC] ✅ 收到 Answer，signalingState={pc.signalingState}，P2P 等待 ICE 建立", flush=True)
            elif "candidate" in data:
                # 收到 ICE candidate，添加到连接
                candidate_text = data["candidate"]
                if not isinstance(candidate_text, str) or not candidate_text.startswith("candidate:"):
                    continue
                candidate = candidate_from_sdp(candidate_text[10:])
                candidate.sdpMid = data.get("sdpMid", data.get("id"))
                candidate.sdpMLineIndex = data.get("sdpMLineIndex", data.get("label"))
                await pc.addIceCandidate(candidate)
                print(f"[ICE] ✅ 已添加远端 Candidate mid={candidate.sdpMid} index={candidate.sdpMLineIndex}", flush=True)
            else:
                print(f"[信令] 收到未知消息字段: {list(data.keys())}", flush=True)
        except Exception as e:
            print(f"[信令-Offerer] 错误: {e}")
            if "closed" in str(e).lower():
                request_restart(str(e))
      request_restart("WebSocket 消息循环结束")
    except websockets.exceptions.ConnectionClosed as e:
      request_restart(f"WebSocket 连接关闭: {e}")


# ========================
# 主运行函数
# ========================
async def run_publisher():
    global source_track, websocket, pc, global_datachannel, p2p_connected, offer_task, bitrate_task, webrtc_latency_profile, restart_requested, offer_in_flight, peer_ready_event
    restart_requested = False
    offer_in_flight = False

    loop = asyncio.get_event_loop()
    # === 初始化 LCM 通信器 ===
    lcm_comm = None 
    if LCM_AVAILABLE:
        lcm_comm = LCMCommunicator(
            loop=loop,
            lcm_url=config['lcm']['url'],
            control_channel=config['lcm']['control_channel'],
            state_channel=config['lcm']['state_channel']
        )
        lcm_comm.start()

    # === 生成低时延参数 ===
    webrtc_latency_profile = build_webrtc_latency_profile()

    # === 初始化视频轨道 ===
    if config.get('use_camera', True):
        # 使用真实摄像头
        try:
            camera_config = config.get('camera', {})
            source_type = str(camera_config.get('source_type', 'usb')).strip().lower()
            camera_width = int(camera_config.get('width', 1920))
            camera_height = int(camera_config.get('height', 1080))
            camera_fps = int(camera_config.get('fps', 30))
            if webrtc_latency_profile.get('enabled'):
                target_fps = min(camera_fps, int(webrtc_latency_profile.get('max_fps', camera_fps)))
                if target_fps != camera_fps:
                    print(f"[低时延] 帧率从 {camera_fps} 限制到 {target_fps} fps 以降低端到端时延")
                camera_fps = target_fps
                print(f"[低时延] 码率配置 min/start/max = {webrtc_latency_profile['min_bitrate_kbps']}/{webrtc_latency_profile['start_bitrate_kbps']}/{webrtc_latency_profile['max_bitrate_kbps']} kbps")

            if source_type == 'usb':
                source_track = USBCameraTrack(
                    device_index=camera_config.get('device_index', 4),
                    width=camera_width,
                    height=camera_height,
                    fps=camera_fps,
                    low_latency=webrtc_latency_profile.get('enabled', False)
                )
                print("[初始化] ✅ 使用 USB 摄像头")
            elif source_type == 'rtsp':
                rtsp_url = str(camera_config.get('rtsp_url', '')).strip()
                source_track = RTSPCameraTrack(
                    rtsp_url=rtsp_url,
                    width=camera_width,
                    height=camera_height,
                    fps=camera_fps,
                    low_latency=webrtc_latency_profile.get('enabled', False)
                )
                print(f"[初始化] ✅ 使用 RTSP 数据流: {sanitize_rtsp_url(rtsp_url)}")
            else:
                raise ValueError(f"不支持的 camera.source_type: {source_type}（支持 usb/rtsp）")
        except Exception as e:
            print(f"[初始化] ❌ 视频源初始化失败: {e}，使用虚拟轨道")
            source_track = DummyVideoTrack(
                width=config.get('camera', {}).get('width', 1920),
                height=config.get('camera', {}).get('height', 1080),
                fps=config.get('camera', {}).get('fps', 30)
            )
    else:
        # 使用虚拟摄像头
        camera_config = config.get('camera', {})
        source_track = DummyVideoTrack(
            width=camera_config.get('width', 1920),
            height=camera_config.get('height', 1080),
            fps=camera_config.get('fps', 30)
        )
        print("[初始化] ✅ 使用虚拟摄像头（use_camera=false）")
        
    # 启动终端输入监听任务
    sender_task = asyncio.create_task(stdin_sender())

    try:
        # 连接到信令服务器（WebSocket）
        async with websockets.connect(config['signaling']['server']) as ws:
            websocket = ws
            print(f"[信令] 已连接到 {config['signaling']['server']}")

            # 先注册 publisher，并启动接收循环等待外部 App 接入通知。
            peer_ready_event = asyncio.Event()
            signaling_task = asyncio.create_task(handle_signaling_as_offerer())
            await send_signaling({"type": "register", "role": "publisher"})
            print("[信令] 已注册为 publisher，等待外部客户端连接...", flush=True)

            # 创建 WebRTC 对等连接（不使用 STUN/TURN）
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            # 添加视频轨道
            pc.addTrack(source_track)
            # 启动实时上行速率监控
            bitrate_task = asyncio.create_task(monitor_upload_kbps(interval=1.0))

            # 创建 DataChannel 用于双向文本通信
            global_datachannel = pc.createDataChannel("chat")
            print("[DataChannel] 已创建通道 'chat'")

            # 监听 DataChannel 打开事件
            @global_datachannel.on("open")
            def on_open():
                print("[DataChannel] 通道已打开")

            # 监听 DataChannel 消息事件
            @global_datachannel.on("message")
            def on_message(message):
                # 收到消息
                # print(f"[DataChannel] ← 收到: {message}")
                messages.append(f"← {message}")


                # 使用 LCM 通信器发送命令
                if lcm_comm:
                    try:
                        data = json.loads(message)
                        lcm_comm.send_command(data)
                    except json.JSONDecodeError as e:
                        print(f"[DataChannel] JSON 解析失败: {e}")

            # 设置 LCM 状态回调：收到状态后通过 DataChannel 发送
            if lcm_comm:
                def on_robot_state(json_state):
                    if global_datachannel and global_datachannel.readyState == "open":
                        global_datachannel.send(json.dumps(json_state))
                lcm_comm.on_state_callback = on_robot_state


            # 监听 WebRTC 连接状态变化
            @pc.on("connectionstatechange")
            async def on_connection_state_change():
                global p2p_connected
                state = pc.connectionState
                print(f"[WebRTC] 连接状态: {state}")
                if state in ["failed", "closed", "disconnected"]:
                    p2p_connected = False
                    print("[WebRTC] ⚠️ P2P 连接断开，将重新发送 Offer")
                    request_restart(f"PeerConnection 状态: {state}")
                elif state == "connected":
                    p2p_connected = True

            # 强制使用 VP8 视频编码（兼容性好）
            transceiver = pc.getTransceivers()[0]  # 获取第一个（视频）收发器
            codecs = RTCRtpSender.getCapabilities("video").codecs  # 获取支持的编解码器
            vp8_codecs = [c for c in codecs if c.mimeType == "video/VP8"]
            if vp8_codecs:
                transceiver.setCodecPreferences(vp8_codecs)
                print("[WebRTC] 💾 已设置仅使用 VP8 编码")
            # # 尝试使用 H.264 编码（低延迟，硬件加速）
            # transceiver = pc.getTransceivers()[0]
            # codecs = RTCRtpSender.getCapabilities("video").codecs
            # h264_codecs = [c for c in codecs if c.mimeType == "video/H264"]

            # if h264_codecs:
            #     transceiver.setCodecPreferences(h264_codecs)
            #     print("[WebRTC] 💾 已设置使用 H264 编码 (低延迟)")
            # else:
            #     # 如果环境不支持 H264，回退到 VP8
            #     vp8_codecs = [c for c in codecs if c.mimeType == "video/VP8"]
            #     if vp8_codecs:
            #         transceiver.setCodecPreferences(vp8_codecs)
            #         print("[WebRTC] ⚠️ H264 不可用，回退到 VP8")
            #     else:
            #         print("[WebRTC] ❌ 错误：无可用视频编码器")
            # 外部客户端接入前不发送 Offer，避免 Offer 被提前消费或丢失。
            await peer_ready_event.wait()
            await create_and_send_offer()

            # 启动定时发送 Offer 的后台任务
            offer_task = asyncio.create_task(offer_sender())

            # 持续处理 Answer 和 ICE candidates。
            await signaling_task

    except websockets.exceptions.ConnectionClosed as e:
        request_restart(f"WebSocket 断开: {e}")
        print(f"[Publisher] 信令连接断开: {e}")
    except Exception as e:
        print(f"[Publisher] 连接失败: {e}")
        request_restart(str(e))
    finally:
        # 清理资源
        if lcm_comm:
            lcm_comm.stop()
            
        if offer_task:
            offer_task.cancel()
            try:
                await offer_task
            except asyncio.CancelledError:
                pass
        if 'signaling_task' in locals() and signaling_task:
            signaling_task.cancel()
            try:
                await signaling_task
            except asyncio.CancelledError:
                pass
        if bitrate_task:
            bitrate_task.cancel()
            try:
                await bitrate_task
            except asyncio.CancelledError:
                pass
        sender_task.cancel()
        try:
            await sender_task 
        except asyncio.CancelledError:
            pass
        if pc:
            await pc.close()
        if source_track:
            source_track.stop()


# ========================
# 信号处理器：优雅退出
# ========================
def signal_handler(sig, frame):
    """捕获 Ctrl+C 信号，优雅关闭并打印收到的消息"""
    print("\n[!] 正在关闭发布端...")
    if source_track:
        source_track.stop() 
    print("\n=== 收到的消息 ===")
    for m in messages:
        print(m)
    sys.exit(0)


# ========================
# 程序入口
# ========================
if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    # 启动主协程
    asyncio.run(run_publisher())
