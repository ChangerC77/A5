#!/bin/bash

workspace=$(pwd)

shell_type=${SHELL##*/}
shell_exec="exec $shell_type"

# CAN
gnome-terminal -t "can1" -x bash -c "cd ${workspace}; cd ../../ARX_X5/ARX_CAN/arx_can; ./arx_can1.sh; exec bash;"
sleep 0.3
gnome-terminal -t "can3" -x bash -c "cd ${workspace}; cd ../../ARX_X5/ARX_CAN/arx_can; ./arx_can3.sh; exec bash;"
sleep 0.3


# Ac_one


# Realsense
gnome-terminal --title="realsense" -x $shell_type -i -c "cd ${workspace}; cd ../realsense; ./realsense.sh; $shell_exec"
sleep 3

# Collect
gnome-terminal --title="collect" -x $shell_type -i -c "cd ${workspace}; cd ../act; conda activate act; python collect.py --episode_idx -1; $shell_exec"   
