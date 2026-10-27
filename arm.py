import xapi.api as x5
import time


# 双臂 ip
left_arm_ip = "192.168.1.9"
right_arm_ip = "192.168.1.10"
# 双臂句柄号
handle_l = x5.connect(left_arm_ip)    # 左臂控制器的IP地址
handle_r = x5.connect(right_arm_ip)   # 右臂控制器的IP地址


# NORMAL_VISION_NO = 0
# NORMAL_TOOL_INDEX = 0

Place_POS_l = {
    "place": x5.get_pr(handle_l, 2),     # 放料点位
    "prep_pal": x5.get_pr(handle_l, 3),  # 放料准备点位
}

Pick_POS_l = {
    "Start": x5.get_pr(handle_l, 4),      # 程序开始点位
    "prep_pick": x5.get_pr(handle_l, 5),  # 抓取准备点位
    "grab": x5.get_pr(handle_l, 6),       # 抓取点位
}


Place_POS_r = {
    "place": x5.get_pr(handle_r, 2),     # 放料点位
    "prep_pal": x5.get_pr(handle_r, 3),  # 放料准备点位
}

Pick_POS_r = {
    "Start": x5.get_pr(handle_r, 4),      # 程序开始点位
    "prep_pick": x5.get_pr(handle_r, 5),  # 抓取准备点位
    "grab": x5.get_pr(handle_r, 6),       # 抓取点位
}


def run_dual_movj(handle_l, handle_r, point_l, point_r):
    # 双臂同时运动到指定点位
    x5.movj(handle_r, point_r)
    x5.movj(handle_l, point_l)
    
    x5.wait_move_done(handle_r)
    x5.wait_move_done(handle_l)

def init_dual_arm():
    # 初始化双臂
    x5.reset(handle_l)
    x5.reset(handle_r)
    x5.abort(handle_l)
    x5.abort(handle_r)
    
    x5.set_remote(handle_l, False)
    x5.set_remote(handle_r, False)

    x5.set_system_mode( handle_l, x5.SYSTEM_MODE_AUTOCMD)
    x5.set_system_mode(handle_r, x5.SYSTEM_MODE_AUTOCMD)

    x5.enable_servo(handle_l, True)  # 启动左臂伺服
    x5.enable_servo(handle_r, True)  # 启动右臂伺服
    x5.set_speed(handle_l, 5)  # 设置左臂速度为 5
    x5.set_speed(handle_r, 5)  # 设置右臂速度为 5

    run_dual_movj(handle_l, handle_r, 
                  Pick_POS_l["Start"], Pick_POS_r["Start"])

    time.sleep(1)  # 等待一段时间，确保速度设置生效


def right_arm_pick_and_place():
    # 右臂抓取和放置操作
    x5.movj(handle_r, Pick_POS_r["prep_pick"])
    x5.movj(handle_r, Pick_POS_r["grab"])
    x5.wait_move_done(handle_r)

    x5.set_do(handle_r, 0, 1) # 右臂吸气
    time.sleep(1)  # 等待吸气完成

    x5.movj(handle_r, Pick_POS_r["prep_pick"])
    x5.movj(handle_r, Place_POS_r["prep_pal"])
    x5.wait_move_done(handle_r)

    x5.movj(handle_r, Place_POS_r["place"])
    x5.wait_move_done(handle_r)

    time.sleep(0.5)  
    # 右臂最后的状态是吸气状态，吹气状态由左手臂控制，等待左臂吹气完成后再关闭右臂吸气



def left_arm_pick_and_place():
    # 左臂抓取和放置操作
    x5.movj(handle_l, Pick_POS_l["prep_pick"])
    x5.movj(handle_l, Pick_POS_l["grab"])
    x5.wait_move_done(handle_l)

    # 左右臂交接动作
    x5.set_do(handle_l, 0, 1) # 左臂吸气
    time.sleep(0.5)  # 等待吸气完成
    x5.set_do(handle_r, 0, 0) # 右臂吸气 关闭
    x5.set_do(handle_r, 1, 1) # 右臂吹气
    time.sleep(0.5)  # 等待吹气完成
    x5.set_do(handle_r, 1, 0) # 右臂吹气 关闭


    x5.movj(handle_l, Pick_POS_l["prep_pick"])
    x5.movj(handle_l, Place_POS_l["prep_pal"])
    x5.wait_move_done(handle_l)

    x5.movj(handle_l, Place_POS_l["place"])
    x5.wait_move_done(handle_l)

    x5.set_do(handle_l, 0, 0) # 左臂吸气关闭
    x5.set_do(handle_l, 1, 1) # 左臂吹气



def main():
    x5.enable_debug_output(True)    # 开启X5 SDK调试输出，便于查看日志信息
    init_dual_arm()

    right_arm_pick_and_place()

    left_arm_pick_and_place()



if __name__ == "__main__":
    main()