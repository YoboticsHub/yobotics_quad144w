#!/bin/bash
# Conda 环境一键配置脚本
# 用于创建和配置四足机器人控制器的 conda 环境

set -e

# 获取脚本所在目录的绝对路径（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  四足机器人控制器 - Conda 环境配置"
echo "=========================================="
echo "项目根目录: $PROJECT_ROOT"
echo ""

# 检查 conda 是否安装
if ! command -v conda &> /dev/null; then
    echo "错误: 未找到 conda 命令"
    echo "请先安装 Anaconda 或 Miniconda"
    echo "下载地址: https://www.anaconda.com/products/distribution"
    exit 1
fi

# 初始化 conda（如果尚未初始化）
if [ -z "$CONDA_DEFAULT_ENV" ]; then
    eval "$(conda shell.bash hook)"
fi

# 提示用户输入环境名
read -p "请输入 conda 环境名称 [默认: robot_controller]: " ENV_NAME
ENV_NAME=${ENV_NAME:-robot_controller}

echo ""
echo "环境名称: $ENV_NAME"
echo ""

# 检查环境是否存在
if conda env list | grep -q "^${ENV_NAME}\s"; then
    echo "环境 '$ENV_NAME' 已存在，将使用现有环境"
    echo "正在激活环境..."
    conda activate "$ENV_NAME"
    echo "环境已激活"
else
    echo "环境 '$ENV_NAME' 不存在，正在创建新环境..."
    echo ""
    
    # 创建 conda 环境（Python 3.8，兼容性较好）
    conda create -n "$ENV_NAME" python=3.8 -y
    
    # 激活环境
    echo "正在激活环境..."
    conda activate "$ENV_NAME"
    echo "环境已创建并激活"
fi

echo ""
echo "=========================================="
echo "  安装系统依赖"
echo "=========================================="
echo ""

# 检查是否为 Ubuntu/Debian 系统
if command -v apt-get &> /dev/null; then
    echo "检测到 Ubuntu/Debian 系统，安装系统依赖..."
    
    # 检查是否需要 sudo
    if [ "$EUID" -eq 0 ]; then
        APT_CMD="apt-get"
    else
        APT_CMD="sudo apt-get"
    fi
    
    $APT_CMD update
    $APT_CMD install -y liblcm-dev libeigen3-dev
    
    echo "系统依赖安装完成"
else
    echo "警告: 未检测到 apt-get，请手动安装以下依赖："
    echo "  - liblcm-dev"
    echo "  - libeigen3-dev"
fi

echo ""
echo "=========================================="
echo "  安装 Conda 依赖包"
echo "=========================================="
echo ""

# 安装 LCM 和 Eigen 库
echo "正在安装 LCM 和 Eigen 库..."
#conda install -c conda-forge lcm eigen -y
conda install -y eigen

echo "Conda 依赖包安装完成"

echo ""
echo "=========================================="
echo "  安装 Python 依赖"
echo "=========================================="
echo ""

# 安装 Python 依赖
echo "正在安装 Python 包..."
pip install --upgrade pip

# 安装指定版本的包
echo "正在安装指定版本的 Python 包..."
pip install numpy==1.24.4 mujoco==3.2.3 pyyaml onnx==1.17.0 websockets aiortc opencv-python

# 安装 ONNX Runtime（用于加载 ONNX 模型）
echo "正在安装 ONNX Runtime 1.19.2..."
if pip install onnxruntime==1.19.2 2>/dev/null; then
    echo "ONNX Runtime 1.19.2 安装成功（通过 pip）"
elif conda install -c conda-forge onnxruntime=1.19.2 -y 2>/dev/null; then
    echo "ONNX Runtime 1.19.2 安装成功（通过 conda-forge）"
else
    echo "警告: 无法自动安装 ONNX Runtime 1.19.2"
    echo "请手动安装: pip install onnxruntime==1.19.2"
fi

# 安装 Python LCM 绑定
echo "正在安装 Python LCM 绑定..."
# 尝试通过 pip 安装
if pip install python-lcm 2>/dev/null || pip install lcm 2>/dev/null; then
    echo "Python LCM 安装成功（通过 pip）"
elif conda install -c conda-forge python-lcm -y 2>/dev/null; then
    echo "Python LCM 安装成功（通过 conda-forge）"
else
    echo "警告: 无法自动安装 Python LCM 绑定"
    echo "请运行以下脚本手动安装:"
    echo "  ./scripts/install_python_lcm.sh"
    echo ""
    echo "注意: 仿真模式可以在没有 LCM 的情况下运行（功能受限）"
fi

echo ""
echo "=========================================="
echo "  配置库路径"
echo "=========================================="
echo ""

# 设置库路径
LIB_PATH="$PROJECT_ROOT/lib"
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$LIB_PATH

# 创建激活脚本，用于在 conda 环境中自动设置库路径
ACTIVATE_SCRIPT="$CONDA_PREFIX/etc/conda/activate.d/robot_controller.sh"
DEACTIVATE_SCRIPT="$CONDA_PREFIX/etc/conda/deactivate.d/robot_controller.sh"

mkdir -p "$CONDA_PREFIX/etc/conda/activate.d"
mkdir -p "$CONDA_PREFIX/etc/conda/deactivate.d"

# 创建激活脚本
cat > "$ACTIVATE_SCRIPT" << EOF
#!/bin/bash
# 自动设置库路径
export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:$LIB_PATH
# 设置 pkg-config 和 CMake 查找路径
export PKG_CONFIG_PATH=\$PKG_CONFIG_PATH:\$CONDA_PREFIX/lib/pkgconfig
export CMAKE_PREFIX_PATH=\$CMAKE_PREFIX_PATH:\$CONDA_PREFIX
EOF

# 创建停用脚本
cat > "$DEACTIVATE_SCRIPT" << EOF
#!/bin/bash
# 移除库路径
export LD_LIBRARY_PATH=\$(echo \$LD_LIBRARY_PATH | sed "s|:$LIB_PATH||g" | sed "s|$LIB_PATH:||g" | sed "s|$LIB_PATH||g")
EOF

chmod +x "$ACTIVATE_SCRIPT"
chmod +x "$DEACTIVATE_SCRIPT"

echo "库路径已配置: $LIB_PATH"
echo "已创建自动激活/停用脚本"

echo ""
echo "=========================================="
echo "  配置完成！"
echo "=========================================="
echo ""
echo "环境名称: $ENV_NAME"
echo "项目根目录: $PROJECT_ROOT"
echo ""
echo "使用方法:"
echo "  1. 激活环境: conda activate $ENV_NAME"
echo "  2. 运行仿真: cd $PROJECT_ROOT && bash scripts/start_mujoco.sh --config config_sim.yaml"
echo "  3. 运行硬件: cd $PROJECT_ROOT && sudo bash scripts/run_robot_controller.sh --config config.yaml"
echo "  4. 查看实机姿态: cd $PROJECT_ROOT && bash scripts/start_hardware_viewer.sh"
echo ""
echo "注意:"
echo "  - 每次使用前请先激活 conda 环境: conda activate $ENV_NAME"
echo "  - 库路径会在激活环境时自动设置"
echo "  - ONNX Runtime 库文件已包含在 lib/ 目录中，无需额外安装"
echo ""
