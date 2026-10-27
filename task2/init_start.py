import xapi.api as x5
import time


# 双臂 ip
left_arm_ip = "192.168.1.9"
right_arm_ip = "192.168.1.10"
# 双臂句柄号
handle_l = x5.connect(left_arm_ip)    # 左臂控制器的IP地址
handle_r = x5.connect(right_arm_ip)   # 右臂控制器的IP地址

add_data_fast = x5.MovPointAdd(vel=30)  # 速度为 fast 的附加数据对象
add_data_slow = x5.MovPointAdd(vel=10)  # 速度为 slow 的附加数据对象

    
Place_POS_l = {
    "place1": x5.get_pr(handle_l, 13),     # 放置1
    "place2": x5.get_pr(handle_l, 14),      # 放置2
}

Pick_POS_l = {
    "Start": x5.get_pr(handle_l, 4),      # 程序开始点位
    "prep_pick": x5.get_pr(handle_l, 11),  # 抓取准备点位
    "grab": x5.get_pr(handle_l, 12),        # 抓取点位

}

Pick_POS_r = {
    "Start": x5.get_pr(handle_r, 4),      # 程序开始点位
    "prep_pick": x5.get_pr(handle_r, 11),  # 抓取准备点位
    "waist_up":x5.get_pr(handle_r, 12),          # 右手腰部升高
    "waist_down":x5.get_pr(handle_r, 13),          # 右手腰部下降
    "grab": x5.get_pr(handle_r, 14),        # 抓取点位14，放置保持
}



def run_dual_movj(handle_l, handle_r, point_l, point_r, add_data=None):
    """双臂同时运动到指定点位"""
    print(f"Moving left arm to: {point_l}, right arm to: {point_r}")
    x5.movj(handle_r, point_r, add_data)
    x5.movj(handle_l, point_l, add_data)
    
    x5.wait_move_done(handle_r, -1)
    x5.wait_move_done(handle_l, -1)
     

def init_dual_arm():
    """初始化双臂，设置为自动模式，启动伺服，并将双臂移动到起始位置"""
    # 运动前先清除报警并停止可能残留的运动
    x5.reset(handle_l)
    x5.reset(handle_r)
    x5.abort(handle_l)
    x5.abort(handle_r)

    x5.set_remote(handle_l, False)
    x5.set_remote(handle_r, False)

    x5.set_system_mode(handle_l, x5.SYSTEM_MODE_AUTOCMD)
    x5.set_system_mode(handle_r, x5.SYSTEM_MODE_AUTOCMD)

    x5.enable_servo(handle_l, True)  # 启动左臂伺服
    x5.enable_servo(handle_r, True)  # 启动右臂伺服
    x5.set_speed(handle_l, 10)  # 设置左臂速度为 10
    x5.set_speed(handle_r, 10)  # 设置右臂速度为 10

    run_dual_movj(handle_l, handle_r, 
                  Pick_POS_l["Start"], Pick_POS_r["Start"])

    time.sleep(1)  # 等待一段时间，确保速度设置生效


def do_dual_pick():

    # 双手准备点位
    run_dual_movj(handle_l, handle_r, 
                  Pick_POS_l["prep_pick"], Pick_POS_r["prep_pick"], ) # 
    
    time.sleep(0.5)

    run_dual_movj(handle_l, handle_r, 
                  Pick_POS_l["prep_pick1"], Pick_POS_r["prep_pick1"], ) # 5, 5
    
    run_dual_movj(handle_l, handle_r, 
                  Pick_POS_l["grab"], Pick_POS_r["grab"], ) 

    run_dual_movj(handle_l, handle_r, 
                Pick_POS_l["grab"], Pick_POS_r["waist_up"], ) # 8, 8

    # run_dual_movj(handle_l, handle_r, 
    #               Pick_POS_l["grab"], Pick_POS_r["waist_up"], )
    
    # run_dual_movj(handle_l, handle_r, 
    #               Pick_POS_l["End"], Pick_POS_r["End"], )


def main():
    x5.enable_debug_output(True)    # 开启X5 SDK调试输出，便于查看日志信息
    
    init_dual_arm()

    # do_dual_pick()



if __name__ == "__main__":
    main()
