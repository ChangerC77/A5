#!/bin/bash
shell_type=${SHELL##*/}
shell_exec="exec $shell_type"
cd realsense
source install/setup.bash
./realsense.sh
cd ..
gnome-terminal --tab --title="can1" -- $shell_type -c "ARX_CAN/arx_can1; $shell_exec" \
             --tab --title="can3" -- $shell_type -c "ARX_CAN/arx_can3; $shell_exec"