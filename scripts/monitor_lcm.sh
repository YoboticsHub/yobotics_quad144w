#!/bin/bash
#
# LCM 通道监控启动脚本 - 自动检测所有通道
# 作者: Han Jiang (jh18954242606@163.com)
# 日期: 2026-01
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 检查网络接口多播支持
check_multicast_support() {
    echo "检查网络接口多播支持..."
    echo "----------------------------------------"
    
    # 查找活动的以太网接口
    interfaces=$(ip link show 2>/dev/null | grep -E "^[0-9]+: (eth|enp|eno|ens)" | \
        awk -F': ' '{print $2}' | awk '{print $1}' || true)
    
    if [ -z "$interfaces" ]; then
        echo -e "${YELLOW}警告: 未找到以太网接口${NC}"
        return 1
    fi
    
    multicast_ok=false
    for iface in $interfaces; do
        # 检查接口是否启用
        if ip link show "$iface" 2>/dev/null | grep -q "state UP"; then
            # 检查是否支持多播
            if ip link show "$iface" 2>/dev/null | grep -q MULTICAST; then
                echo -e "${GREEN}✓${NC} 接口 $iface: 支持多播"
                multicast_ok=true
            else
                echo -e "${RED}✗${NC} 接口 $iface: 不支持多播"
            fi
        else
            echo -e "${YELLOW}○${NC} 接口 $iface: 未启用"
        fi
    done
    
    echo ""
    if [ "$multicast_ok" = false ]; then
        echo -e "${YELLOW}警告: 未找到支持多播的活动接口${NC}"
        echo "请运行网络配置脚本:"
        echo "  sudo bash $SCRIPT_DIR/setup_lcm_network.sh"
        echo ""
        read -p "是否继续? [y/N]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # 检查多播路由
    echo "检查多播路由..."
    if ip route show 2>/dev/null | grep -q "224.0.0.0/4"; then
        echo -e "${GREEN}✓${NC} 多播路由已配置"
    else
        echo -e "${YELLOW}○${NC} 未找到多播路由（可能需要配置）"
        echo "提示: 运行 'sudo bash $SCRIPT_DIR/setup_lcm_network.sh' 配置"
    fi
    echo ""
}

# 检查 Python 环境
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python"
elif [ -n "$CONDA_DEFAULT_ENV" ]; then
    PYTHON_CMD="$(which python)"
else
    PYTHON_CMD="python3"
fi

# 检查网络配置
check_multicast_support

echo "检查 Python 依赖..."
if ! "$PYTHON_CMD" -c "import lcm" 2>/dev/null; then
    echo "错误: 未安装 lcm Python 包"
    echo "请运行: pip install lcm"
    exit 1
fi

if ! "$PYTHON_CMD" -c "import matplotlib" 2>/dev/null; then
    echo "警告: 未安装 matplotlib，将使用文本模式"
    NO_GUI_FLAG="--no-gui"
else
    NO_GUI_FLAG=""
fi

# 检查 LCM 类型文件是否存在（可选）
LCM_TYPES_DIR="$PROJECT_ROOT/lcm-types/python"
if [ ! -f "$LCM_TYPES_DIR/quad_joint_command_t.py" ] || \
   [ ! -f "$LCM_TYPES_DIR/microstrain_lcmt.py" ]; then
    echo "警告: LCM Python 类型文件不存在，正在生成..."
    cd "$PROJECT_ROOT"
    if [ -f "scripts/generate_lcm_types.sh" ]; then
        bash scripts/generate_lcm_types.sh
        if [ $? -ne 0 ]; then
            echo "警告: LCM 类型文件生成失败，将使用原始数据处理"
        fi
    else
        echo "警告: 未找到 generate_lcm_types.sh，将使用原始数据处理"
    fi
fi

# 解析命令行参数
LCM_URL=""
USE_NO_GUI=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --lcm-url)
            LCM_URL="$2"
            shift 2
            ;;
        --no-gui)
            USE_NO_GUI="--no-gui"
            shift
            ;;
        -h|--help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --lcm-url URL    指定 LCM URL (默认: 使用默认 URL)"
            echo "  --no-gui         禁用 GUI，使用文本模式"
            echo "  -h, --help       显示此帮助信息"
            echo ""
            echo "功能:"
            echo "  自动检测所有 LCM 通道并显示通道名称和频率"
            echo "  支持机器人姿态可视化（GUI模式）"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 构建命令
CMD="$PYTHON_CMD $SCRIPT_DIR/monitor_lcm.py"

if [ -n "$LCM_URL" ]; then
    CMD="$CMD --lcm-url \"$LCM_URL\""
fi

if [ -n "$USE_NO_GUI" ]; then
    CMD="$CMD $USE_NO_GUI"
fi

# 显示 LCM URL 信息
echo "========================================"
echo "  LCM 配置信息"
echo "========================================"
if [ -n "$LCM_URL" ]; then
    echo "LCM URL (环境变量): $LCM_URL"
else
    echo "LCM URL: 使用默认 (udpm://239.255.76.67:7667)"
fi
echo ""
            echo "功能说明:"
            echo "  - 自动检测所有 LCM 通道"
            echo "  - 10Hz 实时显示通道名称和频率（顺序稳定）"
            echo "  - GUI 模式支持选择变量绘制曲线"
echo ""
echo "提示: 如果无法接收数据，请检查:"
echo "  1. 网络接口是否支持多播: sudo bash $SCRIPT_DIR/setup_lcm_network.sh"
echo "  2. 防火墙是否允许多播流量"
echo "  3. LCM URL 是否正确配置"
echo "  4. 发送端是否正在运行并发布消息"
echo ""

# 运行监控脚本
cd "$PROJECT_ROOT"
echo "========================================"
echo "  启动 LCM 通道监控器"
echo "========================================"
echo "项目根目录: $PROJECT_ROOT"
echo "Python: $PYTHON_CMD"
echo "========================================"
echo ""

eval $CMD
