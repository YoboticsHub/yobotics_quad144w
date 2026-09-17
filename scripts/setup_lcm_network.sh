#!/bin/bash
#
# LCM 网络配置脚本
# 用于配置网络接口以支持 LCM 多播通信
#
# 作者: Han Jiang (jh18954242606@163.com)
# 日期: 2026-01
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "  LCM Network Configuration Script"
echo "========================================"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}错误: 此脚本需要 root 权限来配置网络接口${NC}"
    echo "请使用: sudo bash $0"
    exit 1
fi

# 查找有线网络接口
find_ethernet_interfaces() {
    # 查找所有以太网接口（通常以 eth, enp, eno, ens 开头）
    ip link show | grep -E "^[0-9]+: (eth|enp|eno|ens)" | \
        awk -F': ' '{print $2}' | awk '{print $1}'
}

# 查找无线网络接口
find_wireless_interfaces() {
    # 查找所有无线接口（通常以 wlan, wlp, wlo 开头）
    ip link show | grep -E "^[0-9]+: (wlan|wlp|wlo)" | \
        awk -F': ' '{print $2}' | awk '{print $1}'
}

# 查找回环接口
find_loopback_interfaces() {
    # 查找回环接口
    ip link show | grep -E "^[0-9]+: lo" | \
        awk -F': ' '{print $2}' | awk '{print $1}'
}

# 获取接口类型
get_interface_type() {
    local iface=$1
    if [[ "$iface" == "lo"* ]]; then
        echo "loopback"
    elif [[ "$iface" =~ ^(wlan|wlp|wlo) ]]; then
        echo "wireless"
    elif [[ "$iface" =~ ^(eth|enp|eno|ens) ]]; then
        echo "ethernet"
    else
        echo "unknown"
    fi
}

# 显示当前网络接口状态
show_interface_status() {
    local iface=$1
    echo ""
    echo "接口 $iface 的当前状态:"
    echo "----------------------------------------"
    ip addr show "$iface" 2>/dev/null | grep -E "inet |inet6 " || \
        echo "  未配置 IP 地址"
    echo ""
    echo "多播支持:"
    cat /sys/class/net/"$iface"/flags 2>/dev/null | \
        awk '{if ($1 ~ /MULTICAST/) print "  MULTICAST: 是"; else print "  MULTICAST: 否"}' || \
        echo "  无法检查"
    echo ""
    echo "当前多播路由:"
    ip mroute show 2>/dev/null | grep "$iface" || echo "  无多播路由"
    echo ""
}

# 配置接口支持多播
configure_multicast() {
    local iface=$1
    
    echo -e "${YELLOW}配置接口 $iface 支持多播...${NC}"
    
    # 启用接口（如果未启用）
    ip link set "$iface" up 2>/dev/null || true
    
    # 设置多播标志（通常已经默认启用）
    # 检查是否支持多播
    if ! ip link show "$iface" | grep -q MULTICAST; then
        echo -e "${RED}警告: 接口 $iface 不支持多播${NC}"
        return 1
    fi
    
    # 添加多播路由（如果需要）
    # LCM 默认使用 239.255.76.67:7667
    # 多播组范围: 224.0.0.0/4
    
    # 检查是否已有路由
    if ! ip route show | grep -q "224.0.0.0/4"; then
        echo "添加多播路由..."
        ip route add 224.0.0.0/4 dev "$iface" 2>/dev/null || \
            echo "  路由可能已存在"
    fi
    
    # 设置接口为混杂模式（可选，通常不需要）
    # ip link set "$iface" promisc on
    
    echo -e "${GREEN}接口 $iface 已配置为支持多播${NC}"
    return 0
}

# 检查防火墙设置
check_firewall() {
    echo ""
    echo "检查防火墙设置..."
    echo "----------------------------------------"
    
    # 检查 iptables
    if command -v iptables >/dev/null 2>&1; then
        echo "iptables 规则:"
        iptables -L -n | grep -E "224.0.0.0|239.255" || \
            echo "  未找到 LCM 相关规则（可能需要允许多播）"
    fi
    
    # 检查 ufw
    if command -v ufw >/dev/null 2>&1; then
        echo ""
        echo "ufw 状态:"
        ufw status | head -5
    fi
    
    echo ""
    echo -e "${YELLOW}提示: 如果防火墙阻止了多播流量，可能需要添加规则:${NC}"
    echo "  sudo iptables -A INPUT -d 224.0.0.0/4 -j ACCEPT"
    echo "  sudo iptables -A INPUT -d 239.255.0.0/16 -j ACCEPT"
}

# 设置 LCM 环境变量
set_lcm_interface() {
    local iface=$1
    local iface_type=$2
    local interface_ip=$3
    
    echo ""
    echo "========================================"
    echo "  设置 LCM 使用指定网卡"
    echo "========================================"
    
    # 根据接口类型生成 LCM URL
    case "$iface_type" in
        "loopback")
            lcm_url="udpm://239.255.76.67:7667?ttl=0"
            echo -e "${YELLOW}注意: 使用回环接口，只能本机通信${NC}"
            ;;
        "wireless"|"ethernet")
            if [ -n "$interface_ip" ]; then
                # 使用指定接口的IP地址
                lcm_url="udpm://239.255.76.67:7667?interface=$interface_ip&ttl=1"
            else
                # 使用接口名称
                lcm_url="udpm://239.255.76.67:7667?ttl=1"
                echo -e "${YELLOW}警告: 接口未配置IP，使用默认多播地址${NC}"
            fi
            ;;
        *)
            lcm_url="udpm://239.255.76.67:7667?ttl=1"
            ;;
    esac
    
    echo ""
    echo "接口信息:"
    echo "  名称: $iface"
    echo "  类型: $iface_type"
    if [ -n "$interface_ip" ]; then
        echo "  IP地址: $interface_ip"
    fi
    echo ""
    echo "LCM URL: $lcm_url"
    echo ""
    
    # 生成配置文件路径
    config_file="$HOME/.lcm_network_config"
    
    # 写入配置文件
    cat > "$config_file" << EOF
# LCM 网络配置
# 生成时间: $(date)
# 接口: $iface
# 类型: $iface_type
export LCM_DEFAULT_URL="$lcm_url"
export LCM_INTERFACE="$iface"
export LCM_INTERFACE_IP="$interface_ip"
EOF
    
    echo -e "${GREEN}配置已保存到: $config_file${NC}"
    echo ""
    echo "使用方法:"
    echo "  1. 在当前终端生效:"
    echo "     source $config_file"
    echo ""
    echo "  2. 永久生效（添加到 ~/.bashrc 或 ~/.zshrc）:"
    echo "     echo 'source $config_file' >> ~/.bashrc"
    echo ""
    echo "  3. 在脚本中使用:"
    echo "     export LCM_DEFAULT_URL=\"$lcm_url\""
    echo ""
}

# 主函数
main() {
    # 获取所有接口类型
    ethernet_ifaces=($(find_ethernet_interfaces))
    wireless_ifaces=($(find_wireless_interfaces))
    loopback_ifaces=($(find_loopback_interfaces))
    
    echo "检测到的网络接口:"
    echo "========================================"
    
    # 显示有线网卡
    if [ ${#ethernet_ifaces[@]} -gt 0 ]; then
        echo "有线网络接口 (Ethernet):"
        for i in "${!ethernet_ifaces[@]}"; do
            iface=${ethernet_ifaces[$i]}
            ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -E "inet " | awk '{print $2}' | cut -d'/' -f1 | head -1)
            status="未配置IP"
            [ -n "$ip_addr" ] && status="IP: $ip_addr"
            echo "  [$((i+1))] $iface - $status"
        done
        echo ""
    fi
    
    # 显示无线网卡
    if [ ${#wireless_ifaces[@]} -gt 0 ]; then
        echo "无线网络接口 (Wireless):"
        for i in "${!wireless_ifaces[@]}"; do
            iface=${wireless_ifaces[$i]}
            ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -E "inet " | awk '{print $2}' | cut -d'/' -f1 | head -1)
            status="未配置IP"
            [ -n "$ip_addr" ] && status="IP: $ip_addr"
            echo "  [$((i+1))] $iface - $status"
        done
        echo ""
    fi
    
    # 显示回环接口
    if [ ${#loopback_ifaces[@]} -gt 0 ]; then
        echo "回环接口 (Loopback):"
        for i in "${!loopback_ifaces[@]}"; do
            iface=${loopback_ifaces[$i]}
            ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -E "inet " | awk '{print $2}' | cut -d'/' -f1 | head -1)
            echo "  [$((i+1))] $iface - $ip_addr"
        done
        echo ""
    fi
    
    # 如果没有任何接口
    total_ifaces=$((${#ethernet_ifaces[@]} + ${#wireless_ifaces[@]} + ${#loopback_ifaces[@]}))
    if [ $total_ifaces -eq 0 ]; then
        echo -e "${RED}错误: 未找到任何网络接口${NC}"
        exit 1
    fi
    
    # 让用户选择接口类型
    echo "请选择要使用的接口类型:"
    option_num=1
    declare -A option_map
    declare -A option_ifaces
    
    if [ ${#ethernet_ifaces[@]} -gt 0 ]; then
        echo "  [$option_num] 有线网络 (Ethernet)"
        option_map[$option_num]="ethernet"
        option_ifaces[$option_num]="${ethernet_ifaces[@]}"
        option_num=$((option_num+1))
    fi
    
    if [ ${#wireless_ifaces[@]} -gt 0 ]; then
        echo "  [$option_num] 无线网络 (Wireless)"
        option_map[$option_num]="wireless"
        option_ifaces[$option_num]="${wireless_ifaces[@]}"
        option_num=$((option_num+1))
    fi
    
    if [ ${#loopback_ifaces[@]} -gt 0 ]; then
        echo "  [$option_num] 本地回环 (Loopback)"
        option_map[$option_num]="loopback"
        option_ifaces[$option_num]="${loopback_ifaces[@]}"
        option_num=$((option_num+1))
    fi
    
    echo ""
    read -p "请选择 [1-$((option_num-1))]: " type_choice
    
    if [ -z "$type_choice" ] || [ "$type_choice" -lt 1 ] || [ "$type_choice" -ge $option_num ]; then
        echo -e "${RED}错误: 无效的选择${NC}"
        exit 1
    fi
    
    selected_type=${option_map[$type_choice]}
    selected_type_ifaces=(${option_ifaces[$type_choice]})
    
    # 如果该类型只有一个接口，直接使用
    if [ ${#selected_type_ifaces[@]} -eq 1 ]; then
        selected_iface=${selected_type_ifaces[0]}
        echo ""
        echo "自动选择接口: $selected_iface"
    else
        # 让用户选择具体接口
        echo ""
        echo "该类型下的接口:"
        for i in "${!selected_type_ifaces[@]}"; do
            iface=${selected_type_ifaces[$i]}
            ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -E "inet " | awk '{print $2}' | cut -d'/' -f1 | head -1)
            status="未配置IP"
            [ -n "$ip_addr" ] && status="IP: $ip_addr"
            echo "  [$((i+1))] $iface - $status"
        done
        echo ""
        read -p "请选择具体接口 [1-${#selected_type_ifaces[@]}]: " iface_choice
        
        if [ -z "$iface_choice" ] || [ "$iface_choice" -lt 1 ] || [ "$iface_choice" -gt ${#selected_type_ifaces[@]} ]; then
            echo -e "${RED}错误: 无效的选择${NC}"
            exit 1
        fi
        
        selected_iface=${selected_type_ifaces[$((iface_choice-1))]}
    fi
    
    echo ""
    echo "选择的接口: $selected_iface (类型: $selected_type)"
    
    # 显示当前状态
    show_interface_status "$selected_iface"
    
    # 配置多播（回环接口不需要配置多播）
    if [ "$selected_type" != "loopback" ]; then
        if configure_multicast "$selected_iface"; then
            echo ""
            echo -e "${GREEN}多播配置完成!${NC}"
        else
            echo ""
            echo -e "${YELLOW}警告: 多播配置可能失败，但继续配置LCM${NC}"
        fi
    else
        echo -e "${YELLOW}回环接口无需配置多播${NC}"
    fi
    
    # 检查防火墙（回环接口不需要）
    if [ "$selected_type" != "loopback" ]; then
        check_firewall
    fi
    
    # 获取接口的 IP 地址
    interface_ip=$(ip addr show "$selected_iface" 2>/dev/null | \
        grep -E "inet " | awk '{print $2}' | cut -d'/' -f1 | head -1)
    
    # 设置 LCM 使用指定网卡
    set_lcm_interface "$selected_iface" "$selected_type" "$interface_ip"
    
    echo ""
    echo "测试 LCM 通信:"
    echo "  1. 加载配置: source $HOME/.lcm_network_config"
    echo "  2. 在一个终端运行: lcm-spy"
    echo "  3. 在另一个终端运行: lcm-logger"
    echo "  4. 检查是否能接收到消息"
    echo ""
}

# 运行主函数
main

