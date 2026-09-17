#!/usr/bin/env bash

# Hardware controller launcher for quad144w/Y20W development packages.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/config.yaml" ]; then
    LEGACY_LAYOUT=1
    PROJECT_ROOT="${SCRIPT_DIR}"
else
    LEGACY_LAYOUT=0
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

CONFIG_FILE="${PROJECT_ROOT}/config.yaml"
CONTROLLER_EXE=""
EXTRA_ARGS=()
LCM_IFACE="${LCM_IFACE:-eth0}"

usage() {
    echo "用法: $0 [选项] [控制器可执行文件] [控制器参数...]"
    echo ""
    echo "选项:"
    echo "  --config FILE    指定配置文件路径（默认: PROJECT_ROOT/config.yaml）"
    echo "  --iface IFACE    指定 LCM 多播网卡（默认: \${LCM_IFACE:-eth0}）"
    echo "  -h, --help       显示此帮助信息"
    echo ""
    echo "架构选择:"
    echo "  x86_64           使用 bin/ybt_ctrl 和 lib/"
    echo "  aarch64/arm64    使用 bin/ybt_ctrl 和 lib/（package_robot_dev.sh 按目标架构生成）"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            if [ $# -lt 2 ]; then
                echo "错误: --config 需要指定文件路径"
                exit 1
            fi
            CONFIG_FILE="$2"
            shift 2
            ;;
        --iface)
            if [ $# -lt 2 ]; then
                echo "错误: --iface 需要指定网卡名"
                exit 1
            fi
            LCM_IFACE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [ -z "${CONTROLLER_EXE}" ] && [ -f "$1" ] && [ -x "$1" ]; then
                if [[ "$1" == /* ]]; then
                    CONTROLLER_EXE="$1"
                else
                    CONTROLLER_EXE="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
                fi
            else
                EXTRA_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

if [[ "${CONFIG_FILE}" != /* ]]; then
    CONFIG_FILE="${PROJECT_ROOT}/${CONFIG_FILE}"
fi

HOST_ARCH="$(uname -m)"
ARCH_LABEL=""
LIB_DIR=""

if [ "${LEGACY_LAYOUT}" -eq 1 ]; then
    LIB_DIR="${PROJECT_ROOT}"
    case "${HOST_ARCH}" in
        x86_64)
            ARCH_LABEL="x86_64"
            ;;
        aarch64|arm64)
            ARCH_LABEL="RK3588/aarch64"
            ;;
        *)
            echo "错误: 不支持的系统架构: ${HOST_ARCH}"
            echo "当前启动脚本仅支持 x86_64 和 aarch64/arm64"
            exit 1
            ;;
    esac
    if [ -z "${CONTROLLER_EXE}" ]; then
        CONTROLLER_EXE="${PROJECT_ROOT}/ybt_ctrl"
    fi
else
    case "${HOST_ARCH}" in
        x86_64)
            ARCH_LABEL="x86_64"
            ;;
        aarch64|arm64)
            ARCH_LABEL="RK3588/aarch64"
            ;;
        *)
            echo "错误: 不支持的系统架构: ${HOST_ARCH}"
            echo "当前启动脚本仅支持 x86_64 和 aarch64/arm64"
            exit 1
            ;;
    esac
    if [ -z "${CONTROLLER_EXE}" ]; then
        CONTROLLER_EXE="${PROJECT_ROOT}/bin/ybt_ctrl"
    fi
    LIB_DIR="${PROJECT_ROOT}/lib"
fi

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "错误: 配置文件不存在: ${CONFIG_FILE}"
    exit 1
fi

if [ ! -f "${CONTROLLER_EXE}" ]; then
    echo "错误: 找不到当前架构对应的控制器: ${CONTROLLER_EXE}"
    exit 1
fi

if [ ! -d "${LIB_DIR}" ]; then
    echo "错误: 找不到当前架构对应的动态库目录: ${LIB_DIR}"
    exit 1
fi

cd "${PROJECT_ROOT}"

EXISTING_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
EXISTING_LD_LIBRARY_PATH="${EXISTING_LD_LIBRARY_PATH#:}"
if [ -n "${EXISTING_LD_LIBRARY_PATH}" ]; then
    RUNTIME_LD_LIBRARY_PATH="${LIB_DIR}:${EXISTING_LD_LIBRARY_PATH}"
else
    RUNTIME_LD_LIBRARY_PATH="${LIB_DIR}"
fi

echo "=========================================="
echo "启动 quad144w/Y20W 实物控制器"
echo "=========================================="
echo "系统架构: ${HOST_ARCH} (${ARCH_LABEL})"
echo "项目根目录: ${PROJECT_ROOT}"
if [ "${LEGACY_LAYOUT}" -eq 1 ]; then
    echo "部署结构: legacy/build"
else
    echo "部署结构: distribution"
fi
echo "可执行文件: ${CONTROLLER_EXE}"
echo "配置文件: ${CONFIG_FILE}"
echo "库路径: ${LIB_DIR}"
echo "LCM 网卡: ${LCM_IFACE}"
echo "=========================================="
echo ""

#if command -v sudo >/dev/null 2>&1 && command -v ifconfig >/dev/null 2>&1; then
#    sudo ifconfig "${LCM_IFACE}" multicast 2>/dev/null || true
#fi
#if command -v sudo >/dev/null 2>&1 && command -v route >/dev/null 2>&1; then
#    sudo route add -net 224.0.0.0 netmask 240.0.0.0 dev "${LCM_IFACE}" 2>/dev/null || true
#fi

if [ "${EUID}" -eq 0 ]; then
    exec env LD_LIBRARY_PATH="${RUNTIME_LD_LIBRARY_PATH}" "${CONTROLLER_EXE}" --config "${CONFIG_FILE}" "${EXTRA_ARGS[@]}"
else
    exec sudo env LD_LIBRARY_PATH="${RUNTIME_LD_LIBRARY_PATH}" "${CONTROLLER_EXE}" --config "${CONFIG_FILE}" "${EXTRA_ARGS[@]}"
fi
