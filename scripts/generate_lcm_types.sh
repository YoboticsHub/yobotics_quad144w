#!/bin/bash

# 四足机器人 LCM 类型生成脚本
# 作者: Han Jiang (jh18954242606@163.com)
# 日期: 2026-01
# 功能: 将 lcm-types 目录下的 .lcm 文件生成 C++ 和 Python 类型文件

# 不使用 set -e，以便继续处理其他文件即使某些文件失败

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LCM_TYPES_DIR="$PROJECT_ROOT/lcm-types"
CPP_OUTPUT_DIR="$LCM_TYPES_DIR/cpp"
PYTHON_OUTPUT_DIR="$LCM_TYPES_DIR/python"

# 检查 lcm-gen 是否安装
if ! command -v lcm-gen &> /dev/null; then
    echo "错误: lcm-gen 未安装。"
    echo ""
    echo "安装方法："
    echo "  1. 安装系统包: sudo apt-get install liblcm-dev"
    echo "  2. 或安装 Python 包: pip3 install lcm"
    echo "  3. 或从源码编译安装 LCM"
    exit 1
fi

# 检测可用的 Python（按优先级顺序）
PYTHON_CMD=""

# 1. 检查虚拟环境
if [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python"
    echo "检测到虚拟环境: $VIRTUAL_ENV"
elif [ -n "$CONDA_DEFAULT_ENV" ]; then
    PYTHON_CMD=$(which python 2>/dev/null)
    echo "检测到 Conda 环境: $CONDA_DEFAULT_ENV"
fi

# 2. 如果还没有找到，尝试查找安装了 lcm 的 Python
if [ -z "$PYTHON_CMD" ] || ! "$PYTHON_CMD" -c "import lcm" 2>/dev/null; then
    # 尝试常见的 Python 路径
    for python_path in \
        "$HOME/.local/bin/python3" \
        "$HOME/anaconda3/bin/python" \
        "$HOME/miniconda3/bin/python" \
        "$(which python3)" \
        "$(which python)" \
        "/usr/bin/python3" \
        "/usr/local/bin/python3"
    do
        if [ -f "$python_path" ] && "$python_path" -c "import lcm" 2>/dev/null; then
            PYTHON_CMD="$python_path"
            echo "找到安装了 LCM 的 Python: $PYTHON_CMD"
            break
        fi
    done
fi

# 3. 如果还是没找到，使用默认的 python3
if [ -z "$PYTHON_CMD" ]; then
    PYTHON_CMD=$(which python3 2>/dev/null || which python 2>/dev/null || echo "python3")
    echo "使用默认 Python: $PYTHON_CMD"
fi

# 检查 Python LCM 模块是否安装
if ! "$PYTHON_CMD" -c "import lcm" 2>/dev/null; then
    echo "=========================================="
    echo "错误: Python LCM 模块未安装!"
    echo "=========================================="
    echo "尝试使用的 Python: $PYTHON_CMD"
    echo ""
    echo "安装方法："
    echo "  1. 如果使用虚拟环境，请先激活虚拟环境，然后："
    echo "     pip install lcm"
    echo ""
    echo "  2. 如果使用系统 Python："
    echo "     $PYTHON_CMD -m pip install --user lcm"
    echo "     或: sudo $PYTHON_CMD -m pip install lcm"
    echo ""
    echo "  3. 或安装系统包："
    echo "     sudo apt-get install python3-lcm"
    echo ""
    echo "安装完成后，请重新运行此脚本。"
    echo "=========================================="
    exit 1
fi

echo "使用 Python: $PYTHON_CMD"

# 使用 lcm-gen 生成类型。部分系统中的 lcm-gen 是 ELF 二进制，不能用 Python 包装执行。
LCM_GEN_PATH=$(which lcm-gen)
if [ -x "$LCM_GEN_PATH" ]; then
    LCM_GEN_CMD="$LCM_GEN_PATH"
else
    # 如果找不到 lcm-gen，尝试直接使用 Python 模块
    LCM_GEN_CMD="$PYTHON_CMD -m lcm"
fi

# 创建输出目录（如果不存在）
mkdir -p "$CPP_OUTPUT_DIR"
mkdir -p "$PYTHON_OUTPUT_DIR"

echo "=========================================="
echo "四足机器人 LCM 类型生成脚本"
echo "=========================================="
echo "项目根目录: $PROJECT_ROOT"
echo "LCM 类型目录: $LCM_TYPES_DIR"
echo "C++ 输出目录: $CPP_OUTPUT_DIR"
echo "Python 输出目录: $PYTHON_OUTPUT_DIR"
echo ""

# 查找所有 .lcm 文件
LCM_FILES=$(find "$LCM_TYPES_DIR" -maxdepth 1 -name "*.lcm" -type f | sort)

if [ -z "$LCM_FILES" ]; then
    echo "警告: 在 $LCM_TYPES_DIR 目录下未找到 .lcm 文件"
    exit 0
fi

# 统计文件数量
FILE_COUNT=$(echo "$LCM_FILES" | wc -l)
echo "找到 $FILE_COUNT 个 LCM 文件，开始生成..."
echo ""

# 生成 C++ 和 Python 类型文件
CPP_SUCCESS_COUNT=0
CPP_FAIL_COUNT=0
PYTHON_SUCCESS_COUNT=0
PYTHON_FAIL_COUNT=0

for lcm_file in $LCM_FILES; do
    filename=$(basename "$lcm_file" .lcm)
    echo "处理文件: $filename.lcm"
    
    # 生成 C++ 头文件
    echo -n "  [C++] 生成中... "
    CPP_ERROR=$("$LCM_GEN_CMD" -x --cpp-hpath "$CPP_OUTPUT_DIR" "$lcm_file" 2>&1)
    CPP_EXIT_CODE=$?
    if [ $CPP_EXIT_CODE -eq 0 ]; then
        echo "✓ 成功"
        ((CPP_SUCCESS_COUNT++))
    else
        echo "✗ 失败"
        echo "    错误信息: $CPP_ERROR"
        ((CPP_FAIL_COUNT++))
    fi
    
    # 生成 Python 文件
    echo -n "  [Python] 生成中... "
    PYTHON_ERROR=$("$LCM_GEN_CMD" -p --ppath "$PYTHON_OUTPUT_DIR" "$lcm_file" 2>&1)
    PYTHON_EXIT_CODE=$?
    if [ $PYTHON_EXIT_CODE -eq 0 ]; then
        echo "✓ 成功"
        ((PYTHON_SUCCESS_COUNT++))
    else
        echo "✗ 失败"
        echo "    错误信息: $PYTHON_ERROR"
        ((PYTHON_FAIL_COUNT++))
    fi
    echo ""
done

echo "=========================================="
echo "生成完成!"
echo "=========================================="
echo "C++ 类型文件:"
echo "  成功: $CPP_SUCCESS_COUNT 个"
echo "  失败: $CPP_FAIL_COUNT 个"
echo "  输出目录: $CPP_OUTPUT_DIR"
echo ""
echo "Python 类型文件:"
echo "  成功: $PYTHON_SUCCESS_COUNT 个"
echo "  失败: $PYTHON_FAIL_COUNT 个"
echo "  输出目录: $PYTHON_OUTPUT_DIR"
echo "=========================================="

# 检查是否有失败
if [ $CPP_FAIL_COUNT -eq 0 ] && [ $PYTHON_FAIL_COUNT -eq 0 ]; then
    echo "✓ 所有 LCM 类型已成功生成!"
    exit 0
else
    echo "⚠ 警告: 部分文件生成失败，请检查错误信息"
    exit 1
fi
