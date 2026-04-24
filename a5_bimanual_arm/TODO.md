1. 删除控制线程，api中已有内部控制线程了
2. 新增一个fsm低频线程
3. 将recorder集成到fsm线程中
4. 需要考察：现在的obs/qpos是上一帧的action，是否正确？；action是pos，是否要改为dposdt？
