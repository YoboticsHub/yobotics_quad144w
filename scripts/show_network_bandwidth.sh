#!/bin/bash
# 实时网络带宽占用率显示
# 使用方法: ./show_network_bandwidth.sh [network_interface] [interval]
# 示例: ./show_network_bandwidth.sh eth0 1

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取参数
INTERFACE=${1:-""}
INTERVAL=${2:-1}

# 检测网络接口
if [ -z "$INTERFACE" ]; then
    DEFAULT_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
    if [ -z "$DEFAULT_INTERFACE" ]; then
        echo -e "${YELLOW}可用的网络接口:${NC}"
        ip -o link show | awk '{print $2}' | sed 's/:$//' | grep -v lo
        echo ""
        read -p "请输入网络接口名称: " INTERFACE
    else
        INTERFACE=$DEFAULT_INTERFACE
    fi
fi

# 验证接口
if ! ip link show "$INTERFACE" &>/dev/null; then
    echo -e "${RED}错误: 网络接口 '$INTERFACE' 不存在${NC}"
    exit 1
fi

# 获取接口最大速度（如果可用）
MAX_SPEED=0
if command -v ethtool &> /dev/null; then
    SPEED_INFO=$(ethtool $INTERFACE 2>/dev/null | grep -i "Speed:" | grep -oP '\d+' | head -n1)
    if [ ! -z "$SPEED_INFO" ]; then
        MAX_SPEED=$SPEED_INFO
    fi
fi

# 清屏并显示标题
clear
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  实时网络带宽监控 - $INTERFACE${NC}"
echo -e "${CYAN}  按 Ctrl+C 退出${NC}"
if [ "$MAX_SPEED" -gt 0 ]; then
    echo -e "${CYAN}  接口最大速度: ${MAX_SPEED} Mbps${NC}"
fi
echo -e "${CYAN}========================================${NC}"
echo ""

# 获取初始统计
get_stats() {
    if [ -f "/sys/class/net/$INTERFACE/statistics/rx_bytes" ] && [ -f "/sys/class/net/$INTERFACE/statistics/tx_bytes" ]; then
        RX=$(cat /sys/class/net/$INTERFACE/statistics/rx_bytes)
        TX=$(cat /sys/class/net/$INTERFACE/statistics/tx_bytes)
        echo "$RX $TX"
    else
        echo "0 0"
    fi
}

# 格式化速度显示
format_speed() {
    local bytes_per_sec=$1
    local mbps=$(echo "scale=2; $bytes_per_sec * 8 / 1000000" | bc 2>/dev/null || echo "0")
    local kbps=$(echo "scale=2; $bytes_per_sec * 8 / 1000" | bc 2>/dev/null || echo "0")
    
    if (( $(echo "$mbps >= 1" | bc -l 2>/dev/null || echo 0) )); then
        printf "%.2f Mbps" $mbps
    else
        printf "%.2f Kbps" $kbps
    fi
}

# 格式化百分比显示
format_percent() {
    local current=$1
    local max=$2
    
    if [ "$max" -gt 0 ]; then
        local percent=$(echo "scale=1; $current * 100 / $max" | bc 2>/dev/null || echo "0")
        printf "%.1f%%" $percent
    else
        printf "N/A"
    fi
}

# 绘制简单的进度条
draw_bar() {
    local percent=$1
    local width=30
    local filled=$(echo "scale=0; $percent * $width / 100" | bc 2>/dev/null || echo 0)
    local empty=$((width - filled))
    
    printf "["
    for ((i=0; i<filled; i++)); do
        printf "="
    done
    for ((i=0; i<empty; i++)); do
        printf " "
    done
    printf "]"
}

# 获取初始值
INIT_STATS=$(get_stats)
INIT_RX=$(echo $INIT_STATS | awk '{print $1}')
INIT_TX=$(echo $INIT_STATS | awk '{print $2}')

# 主循环
while true; do
    # 获取当前统计
    CURR_STATS=$(get_stats)
    CURR_RX=$(echo $CURR_STATS | awk '{print $1}')
    CURR_TX=$(echo $CURR_STATS | awk '{print $2}')
    
    # 计算差值
    RX_DIFF=$((CURR_RX - INIT_RX))
    TX_DIFF=$((CURR_TX - INIT_TX))
    
    # 计算速率 (bytes per second)
    RX_RATE=$((RX_DIFF / INTERVAL))
    TX_RATE=$((TX_DIFF / INTERVAL))
    TOTAL_RATE=$((RX_RATE + TX_RATE))
    
    # 转换为 Mbps
    RX_MBPS=$(echo "scale=2; $RX_RATE * 8 / 1000000" | bc 2>/dev/null || echo "0")
    TX_MBPS=$(echo "scale=2; $TX_RATE * 8 / 1000000" | bc 2>/dev/null || echo "0")
    TOTAL_MBPS=$(echo "scale=2; $TOTAL_RATE * 8 / 1000000" | bc 2>/dev/null || echo "0")
    
    # 计算占用率
    if [ "$MAX_SPEED" -gt 0 ]; then
        RX_PERCENT=$(echo "scale=1; $RX_MBPS * 100 / $MAX_SPEED" | bc 2>/dev/null || echo "0")
        TX_PERCENT=$(echo "scale=1; $TX_MBPS * 100 / $MAX_SPEED" | bc 2>/dev/null || echo "0")
        TOTAL_PERCENT=$(echo "scale=1; $TOTAL_MBPS * 100 / $MAX_SPEED" | bc 2>/dev/null || echo "0")
    else
        RX_PERCENT=0
        TX_PERCENT=0
        TOTAL_PERCENT=0
    fi
    
    # 清屏并更新显示
    clear
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  实时网络带宽监控 - $INTERFACE${NC}"
    echo -e "${CYAN}  更新时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    if [ "$MAX_SPEED" -gt 0 ]; then
        echo -e "${CYAN}  接口最大速度: ${MAX_SPEED} Mbps${NC}"
    fi
    echo -e "${CYAN}  按 Ctrl+C 退出${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
    
    # 显示接收速率
    echo -e "${GREEN}接收 (RX):${NC}"
    printf "  速率: %-15s" "$(format_speed $RX_RATE)"
    if [ "$MAX_SPEED" -gt 0 ]; then
        printf "  占用率: "
        if (( $(echo "$RX_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${RED}$(format_percent $RX_MBPS $MAX_SPEED)${NC}"
        elif (( $(echo "$RX_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${YELLOW}$(format_percent $RX_MBPS $MAX_SPEED)${NC}"
        else
            echo -e "${GREEN}$(format_percent $RX_MBPS $MAX_SPEED)${NC}"
        fi
        if [ "$MAX_SPEED" -gt 0 ]; then
            printf "  "
            if (( $(echo "$RX_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${RED}$(draw_bar $RX_PERCENT)${NC}"
            elif (( $(echo "$RX_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${YELLOW}$(draw_bar $RX_PERCENT)${NC}"
            else
                echo -e "${GREEN}$(draw_bar $RX_PERCENT)${NC}"
            fi
        fi
    else
        echo ""
    fi
    
    echo ""
    
    # 显示发送速率
    echo -e "${BLUE}发送 (TX):${NC}"
    printf "  速率: %-15s" "$(format_speed $TX_RATE)"
    if [ "$MAX_SPEED" -gt 0 ]; then
        printf "  占用率: "
        if (( $(echo "$TX_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${RED}$(format_percent $TX_MBPS $MAX_SPEED)${NC}"
        elif (( $(echo "$TX_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${YELLOW}$(format_percent $TX_MBPS $MAX_SPEED)${NC}"
        else
            echo -e "${GREEN}$(format_percent $TX_MBPS $MAX_SPEED)${NC}"
        fi
        if [ "$MAX_SPEED" -gt 0 ]; then
            printf "  "
            if (( $(echo "$TX_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${RED}$(draw_bar $TX_PERCENT)${NC}"
            elif (( $(echo "$TX_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${YELLOW}$(draw_bar $TX_PERCENT)${NC}"
            else
                echo -e "${BLUE}$(draw_bar $TX_PERCENT)${NC}"
            fi
        fi
    else
        echo ""
    fi
    
    echo ""
    
    # 显示总速率
    echo -e "${CYAN}总计 (Total):${NC}"
    printf "  速率: %-15s" "$(format_speed $TOTAL_RATE)"
    if [ "$MAX_SPEED" -gt 0 ]; then
        printf "  占用率: "
        if (( $(echo "$TOTAL_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${RED}$(format_percent $TOTAL_MBPS $MAX_SPEED)${NC}"
        elif (( $(echo "$TOTAL_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "${YELLOW}$(format_percent $TOTAL_MBPS $MAX_SPEED)${NC}"
        else
            echo -e "${GREEN}$(format_percent $TOTAL_MBPS $MAX_SPEED)${NC}"
        fi
        if [ "$MAX_SPEED" -gt 0 ]; then
            printf "  "
            if (( $(echo "$TOTAL_PERCENT > 80" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${RED}$(draw_bar $TOTAL_PERCENT)${NC}"
            elif (( $(echo "$TOTAL_PERCENT > 50" | bc -l 2>/dev/null || echo 0) )); then
                echo -e "${YELLOW}$(draw_bar $TOTAL_PERCENT)${NC}"
            else
                echo -e "${CYAN}$(draw_bar $TOTAL_PERCENT)${NC}"
            fi
        fi
    else
        echo ""
        echo -e "${YELLOW}提示: 安装 ethtool 可显示占用率 (sudo apt-get install ethtool)${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}========================================${NC}"
    
    # 更新初始值
    INIT_RX=$CURR_RX
    INIT_TX=$CURR_TX
    
    # 等待
    sleep $INTERVAL
done

