# ARX A5 数据采集
## setup env

## build

## 启动采集

new tab
```
./start.sh
```
new tab
```bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args \
  -p mode:=collect \
  -p datasets_dir:=/home/arx/WBCD/A5/datasets \
  -p img_head_topic:=/camera/camera_h/color/image_rect_raw \
  -p img_left_topic:=/camera/camera_l/color/image_rect_raw \
  -p img_right_topic:=/camera/camera_r/color/image_rect_raw 
```
等待输出
```
[INFO] [1777127994.459202875] [bimanual_arm_controller]: Ready. Press SPACE to start collect, press ESC to quit.
```
按下空格开始采集
```
[INFO] [1777128064.854809231] [bimanual_arm_controller]: Data collection started.
[INFO] [1777128064.855144094] [bimanual_arm_controller]: Episode 0 started
[INFO] [1777128064.862365064] [bimanual_arm_controller]: episode_frames=1
[INFO] [1777128064.873831593] [bimanual_arm_controller]: episode_frames=2
[INFO] [1777128064.884716094] [bimanual_arm_controller]: episode_frames=3
[INFO] [1777128064.896070840] [bimanual_arm_controller]: episode_frames=4
...
```
再按下空格结束采集
```
[INFO] [1777128065.789746096] [bimanual_arm_controller]: Data collection stopped.
[INFO] [1777128065.789960808] [bimanual_arm_controller]: Stopping episode with counts={'timestamp': 67, 'observations/qpos': 67, 'observations/qvel': 67, 'observations/images/head': 67, 'observations/images/left_wrist': 67, 'observations/images/right_wrist': 67, 'actions': 67}, sync_attempts=67, sync_successes=67
[INFO] [1777128065.790115444] [bimanual_arm_controller]: Episode 0 stopped, 67 frames recorded
[INFO] [1777128065.790944621] [bimanual_arm_controller]: Saving 1 episodes to /home/arx/WBCD/A5/datasets/episode_5.hdf5
...
```
如此重复
最后一次采集结束后，等待保存完成再按下ctrl+C
```
[INFO] [1777128069.902915504] [bimanual_arm_controller]: Saved 1 episodes to /home/arx/WBCD/A5/datasets/episode_5.hdf5
```
### 常见问题
```
[WARN] [1777128058.064386214] [bimanual_arm_controller]: No image received on one or more topics yet. Check topic names and publisher QoS compatibility.
```
如果一直出现警告，检查realsense输出，只出现一两次可忽略

## replay
``` bash
ros2 run a5_bimanual_arm bimanual_arm_controller --ros-args \
  -p mode:=replay \
  -p datasets_dir:=/home/arx/WBCD/A5/datasets
```
按空格开始重放最新一次记录