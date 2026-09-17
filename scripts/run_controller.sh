#!/bin/bash
#
# 四足机器人控制器运行脚本
# 用于运行 ybt_ctrl 控制器程序
#
# 作者: Han Jiang (jh18954242606@163.com)
# 日期: 2026-01
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="${SCRIPT_DIR}/.."

# 默认可执行文件路径
CONTROLLER_EXE="${PROJECT_ROOT}/build/user/YBT_Controller/ybt_ctrl"

# 检查可执行文件是否存在
if [ ! -f "${CONTROLLER_EXE}" ]; then
    echo -e "${RED}错误: 找不到控制器可执行文件: ${CONTROLLER_EXE}${NC}"
    echo "请先编译项目: cd build && make -j4"
    exit 1
fi

# 检查配置文件是否存在
if [ ! -f "${PROJECT_ROOT}/config.yaml" ]; then
    echo -e "${YELLOW}警告: 找不到配置文件: ${PROJECT_ROOT}/config.yaml${NC}"
    echo "控制器将尝试在当前目录查找配置文件"
fi

# 检查 URDF 文件是否存在
if [ ! -f "${PROJECT_ROOT}/resources/robots/e3/e3.urdf" ]; then
    echo -e "${YELLOW}警告: 找不到 URDF 文件: ${PROJECT_ROOT}/resources/robots/e3/e3.urdf${NC}"
fi

# 检查 ONNX 模型文件是否存在
if [ ! -d "${PROJECT_ROOT}/actor_model" ]; then
    echo -e "${YELLOW}警告: 找不到 ONNX 模型目录: ${PROJECT_ROOT}/actor_model${NC}"
fi

# 设置库路径
export LD_LIBRARY_PATH="${PROJECT_ROOT}/build/common:${PROJECT_ROOT}/build/robot:${PROJECT_ROOT}/build/third-party/ParamHandler:${PROJECT_ROOT}/build/third-party/lord_imu:${PROJECT_ROOT}/build/third-party/SOEM:${PROJECT_ROOT}/third-party/onnx/lib:${LD_LIBRARY_PATH}"

# 查找 onnxruntime 库
ONNXRUNTIME_LIB=""
# 优先使用项目内的 onnxruntime 库
ONNXRUNTIME_PATHS=(
    "${PROJECT_ROOT}/third-party/onnx/lib/libonnxruntime.so.1"
    "${PROJECT_ROOT}/third-party/onnx/lib/libonnxruntime.so"
    "/usr/lib/onnxruntime-linux-x64-1.20.1/lib/libonnxruntime.so.1"
    "/usr/local/lib/libonnxruntime.so.1"
    "/usr/lib/x86_64-linux-gnu/libonnxruntime.so.1"
    "/opt/onnxruntime/lib/libonnxruntime.so.1"
)

for path in "${ONNXRUNTIME_PATHS[@]}"; do
    if [ -f "${path}" ]; then
        ONNXRUNTIME_LIB="${path}"
        break
    fi
done

# 如果找到了库，添加到库路径
if [ -n "${ONNXRUNTIME_LIB}" ]; then
    ONNXRUNTIME_DIR=$(dirname "${ONNXRUNTIME_LIB}")
    export LD_LIBRARY_PATH="${ONNXRUNTIME_DIR}:${LD_LIBRARY_PATH}"
else
    echo -e "${YELLOW}警告: 找不到 onnxruntime 库${NC}"
    echo "请确保已安装 onnxruntime 或设置正确的库路径"
fi

# 切换到项目根目录（控制器会在此查找配置文件）
cd "${PROJECT_ROOT}"

# 显示运行信息
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  四足机器人控制器启动${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}可执行文件: ${CONTROLLER_EXE}${NC}"
echo -e "${BLUE}工作目录: ${PROJECT_ROOT}${NC}"
echo ""

# 保存库路径（用于 sudo 时传递）
SAVED_LD_LIBRARY_PATH="${LD_LIBRARY_PATH}"

# 检查是否需要 root 权限（硬件模式需要）
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}提示: 当前未以 root 权限运行${NC}"
    echo -e "${YELLOW}硬件模式需要 root 权限（实时调度、硬件访问）${NC}"
    echo -e "${YELLOW}仿真模式通常不需要 root 权限${NC}"
    echo ""
    read -p "是否继续运行? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi
fi

# 运行控制器
echo -e "${GREEN}启动控制器...${NC}"
echo ""

# 捕获 Ctrl+C 信号
trap 'echo -e "\n${YELLOW}正在停止控制器...${NC}"; exit 0' INT TERM

# 如果以 root 身份运行（通过 sudo），确保库路径正确设置
if [ "$EUID" -eq 0 ]; then
    # 如果 LD_LIBRARY_PATH 为空或被重置，使用保存的值
    if [ -z "${LD_LIBRARY_PATH}" ] || [ "${LD_LIBRARY_PATH}" != "${SAVED_LD_LIBRARY_PATH}" ]; then
        export LD_LIBRARY_PATH="${SAVED_LD_LIBRARY_PATH}"
    fi
fi

# 执行控制器
exec "${CONTROLLER_EXE}" "$@"
