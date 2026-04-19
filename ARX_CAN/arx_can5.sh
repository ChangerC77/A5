#!/bin/bash

# 关闭作业控制，避免输出 "Killed" 信息
set +m

source ~/.bashrc

CAN_DEVICE="/dev/arxcan5"
CAN_INTERFACE="can5"

# 状态变量：跟踪上一次的状态，避免重复输出
LAST_STATE=""

# 清理函数：按 Ctrl+C 时执行
cleanup() {
    echo -e "\n收到退出信号，正在停止..."
    exit 0
}

# 捕获 Ctrl+C (SIGINT) 和 kill (SIGTERM)
trap cleanup SIGINT SIGTERM

start_can() {
    # 检查设备文件是否存在
    if [ ! -e "$CAN_DEVICE" ]; then
        if [ "$LAST_STATE" != "waiting" ]; then
            echo "等待设备 $CAN_DEVICE 接入..."
            LAST_STATE="waiting"
        fi
        return 1
    fi

    sudo slcand -o -f -s8 $CAN_DEVICE $CAN_INTERFACE 2>/dev/null
    if [ $? -ne 0 ]; then
        return 1
    fi

    sleep 0.5
    sudo ip link set $CAN_INTERFACE up 2>/dev/null

    if [ $? -ne 0 ]; then
        return 1
    fi

    if [ "$LAST_STATE" != "running" ]; then
        echo "$CAN_INTERFACE 启动成功"
        LAST_STATE="running"
    fi
    return 0
}

check_can() {
    if ip link show "$CAN_INTERFACE" > /dev/null 2>&1; then
        if ip link show "$CAN_INTERFACE" | grep -q "UP"; then
            return 0
        else
            return 1
        fi
    else
        return 2
    fi
}

while true; do
    if check_can; then
        if [ "$LAST_STATE" != "running" ]; then
            echo "$CAN_INTERFACE 正常工作"
            LAST_STATE="running"
        fi
    else
        if [ "$LAST_STATE" != "restarting" ] && [ "$LAST_STATE" != "waiting" ]; then
            echo "$CAN_INTERFACE 掉线，重启中..."
            LAST_STATE="restarting"
        fi

        sudo ip link set $CAN_INTERFACE down 2>/dev/null

        # 先检查进程是否存在，再杀死
        pids=$(pgrep -f "slcand.*$CAN_INTERFACE")
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null
        fi

        sleep 1

        if ! start_can; then
            sleep 1
        fi
    fi

    sleep 1
done
