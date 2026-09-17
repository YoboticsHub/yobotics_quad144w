#!/bin/bash

# MuJoCo 仿真启动脚本
# 作者: Han Jiang (jh18954242606@163.com)
# 日期: 2026-01
# 功能: 启动 MuJoCo 仿真器

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 默认配置文件路径（仿真专用）
CONFIG_FILE="${PROJECT_ROOT}/config_sim.yaml"

# 解析命令行参数
HEADLESS=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --headless)
            HEADLESS=true
            shift
            ;;
        -h|--help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --config FILE    指定配置文件路径（默认: config_sim.yaml）"
            echo "  --headless       无头模式运行（不显示可视化窗口）"
            echo "  -h, --help       显示此帮助信息"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 $0 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    echo "错误: 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

# 检查是否启用 MuJoCo
ENABLE_MUJOCO=$(python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    enable = config.get('simulation', {}).get('enable_mujoco', False)
    print('true' if enable else 'false')
except Exception as e:
    print('false', file=sys.stderr)
    sys.exit(1)
")

if [ "$ENABLE_MUJOCO" != "true" ]; then
    echo "错误: MuJoCo 仿真未启用"
    echo "请在配置文件中设置 simulation.enable_mujoco: true"
    exit 1
fi

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 设置 Python 路径
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"
export YBT_CONFIG_FILE="${CONFIG_FILE}"

# 检测环境类型（分发包还是开发环境）
IS_DISTRIBUTION=false
CONTROLLER_EXE=""
LD_LIBRARY_PATHS=""

# 检查是否是分发包结构（有 bin/ 和 lib/ 目录）
if [ -d "${PROJECT_ROOT}/bin" ] && [ -d "${PROJECT_ROOT}/lib" ] && [ -f "${PROJECT_ROOT}/bin/ybt_ctrl" ]; then
    IS_DISTRIBUTION=true
    CONTROLLER_EXE="${PROJECT_ROOT}/bin/ybt_ctrl"
    LD_LIBRARY_PATHS="${PROJECT_ROOT}/lib"
    echo "检测到分发包环境"
else
    # 开发环境：尝试多个可能的构建目录
    BUILD_DIRS=(
        "${PROJECT_ROOT}/build_lib"
        "${PROJECT_ROOT}/build"
    )
    
    for BUILD_DIR in "${BUILD_DIRS[@]}"; do
        if [ -f "${BUILD_DIR}/user/YBT_Controller/ybt_ctrl" ]; then
            CONTROLLER_EXE="${BUILD_DIR}/user/YBT_Controller/ybt_ctrl"
            LD_LIBRARY_PATHS="${BUILD_DIR}/common:${BUILD_DIR}/robot:${BUILD_DIR}/third-party/ParamHandler:${BUILD_DIR}/third-party/lord_imu:${BUILD_DIR}/third-party/SOEM"
            
            # 添加 ONNX Runtime 库路径
            ONNX_PATHS=(
                "${PROJECT_ROOT}/third-party/onnx/lib"
                "/usr/lib/onnxruntime-linux-x64-1.20.1/lib"
                "/usr/lib/onnxruntime-linux-x64-1.19.2/lib"
                "/usr/local/lib"
            )
            
            for ONNX_PATH in "${ONNX_PATHS[@]}"; do
                if [ -d "$ONNX_PATH" ]; then
                    LD_LIBRARY_PATHS="${LD_LIBRARY_PATHS}:${ONNX_PATH}"
                    break
                fi
            done
            
            echo "检测到开发环境 (构建目录: $BUILD_DIR)"
            break
        fi
    done
fi

# 检查控制器可执行文件
if [ -z "$CONTROLLER_EXE" ] || [ ! -f "$CONTROLLER_EXE" ]; then
    echo "错误: 找不到控制器可执行文件"
    if [ "$IS_DISTRIBUTION" = true ]; then
        echo "分发包中应该存在: ${PROJECT_ROOT}/bin/ybt_ctrl"
    else
        echo "开发环境中应该在以下位置之一："
        echo "  - ${PROJECT_ROOT}/build/user/YBT_Controller/ybt_ctrl"
        echo "  - ${PROJECT_ROOT}/build_lib/user/YBT_Controller/ybt_ctrl"
        echo ""
        echo "请先编译项目:"
        echo "  cd build && cmake .. && make -j4"
        echo "或者:"
        echo "  cd build_lib && cmake -DBUILD_AS_LIBRARY=ON .. && make -j4"
    fi
    exit 1
fi

# 设置库路径
export LD_LIBRARY_PATH="${LD_LIBRARY_PATHS}:${LD_LIBRARY_PATH}"

# 启动 MuJoCo 仿真器
echo "=========================================="
echo "启动 MuJoCo 仿真器和控制器"
echo "=========================================="
echo "环境类型: $([ "$IS_DISTRIBUTION" = true ] && echo "分发包" || echo "开发环境")"
echo "项目根目录: $PROJECT_ROOT"
echo "可执行文件: $CONTROLLER_EXE"
echo "配置文件: $CONFIG_FILE"
echo "无头模式: $HEADLESS"
echo "库路径: $LD_LIBRARY_PATHS"
echo "=========================================="
echo ""

# 保存库路径（用于后台进程）
SAVED_LD_LIBRARY_PATH="${LD_LIBRARY_PATH}"

# 清理函数
cleanup() {
    echo ""
    echo "=========================================="
    echo "正在停止所有进程..."
    echo "=========================================="
    
    # 停止控制器
    if [ -n "${CONTROLLER_PID}" ]; then
        echo "停止控制器 (PID: ${CONTROLLER_PID})..."
        kill "${CONTROLLER_PID}" 2>/dev/null || true
    fi
    
    # 停止 MuJoCo 仿真器（先尝试优雅终止）
    if [ -n "${MUJOCO_PID}" ]; then
        echo "停止 MuJoCo 仿真器 (PID: ${MUJOCO_PID})..."
        kill "${MUJOCO_PID}" 2>/dev/null || true
        
        # 等待进程退出（最多等待2秒）
        for i in {1..20}; do
            if ! kill -0 "${MUJOCO_PID}" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done
        
        # 如果还在运行，强制杀死
        if kill -0 "${MUJOCO_PID}" 2>/dev/null; then
            echo "强制终止 MuJoCo 仿真器..."
            kill -9 "${MUJOCO_PID}" 2>/dev/null || true
        fi
    fi
    
    # 额外清理：杀死所有相关的 python3 mujoco_simulator 进程
    echo "清理残留的 MuJoCo 进程..."
    pkill -f "mujoco_sim.mujoco_simulator" 2>/dev/null || true
    sleep 0.5
    pkill -9 -f "mujoco_sim.mujoco_simulator" 2>/dev/null || true
    
    wait 2>/dev/null || true
    echo "所有进程已停止"
    exit 0
}

# 捕获退出信号
trap cleanup INT TERM EXIT

# 在后台启动 MuJoCo 仿真器
echo "启动 MuJoCo 仿真器（后台运行）..."
if [ "$HEADLESS" = true ]; then
    LD_LIBRARY_PATH="${SAVED_LD_LIBRARY_PATH}" python3 -m mujoco_sim.mujoco_simulator --config "$CONFIG_FILE" --headless &
else
    LD_LIBRARY_PATH="${SAVED_LD_LIBRARY_PATH}" python3 -m mujoco_sim.mujoco_simulator --config "$CONFIG_FILE" &
fi
MUJOCO_PID=$!

# 等待一下，确保仿真器启动
sleep 2

# 检查 MuJoCo 进程是否还在运行
if ! kill -0 "${MUJOCO_PID}" 2>/dev/null; then
    echo "错误: MuJoCo 仿真器启动失败"
    exit 1
fi

echo "MuJoCo 仿真器已启动 (PID: ${MUJOCO_PID})"
echo ""

# 启动控制器（前台运行，这样可以看到输出）
echo "启动控制器..."
echo ""

# 如果以 root 身份运行，确保库路径正确
if [ "$EUID" -eq 0 ]; then
    export LD_LIBRARY_PATH="${SAVED_LD_LIBRARY_PATH}"
fi

# 在前台运行控制器
exec "${CONTROLLER_EXE}" --config "${CONFIG_FILE}" "$@"
