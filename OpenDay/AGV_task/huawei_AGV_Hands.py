import xapi.api as x5
import copy
import threading
import time
import AGV_api as agv
import copy

DEBUG_STEP_MODE = True
DEBUG_STEP_INDEX = 0


def _fmt_num(value, digits=3):
    try:
        number = float(value)
        if abs(number) < 0.0005:
            number = 0.0
        return f"{number:.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_joint(joint):
    return (
        "x5.Joint("
        f"j1={_fmt_num(joint.j1)}, j2={_fmt_num(joint.j2)}, "
        f"j3={_fmt_num(joint.j3)}, j4={_fmt_num(joint.j4)}, "
        f"j5={_fmt_num(joint.j5)}, j6={_fmt_num(joint.j6)}, "
        f"e1={_fmt_num(joint.e1)}, e2={_fmt_num(joint.e2)}, "
        f"e3={_fmt_num(joint.e3)})"
    )


def _format_pose(pose):
    return (
        "x5.Pose("
        f"x={_fmt_num(pose.x)}, y={_fmt_num(pose.y)}, z={_fmt_num(pose.z)}, "
        f"a={_fmt_num(pose.a)}, b={_fmt_num(pose.b)}, c={_fmt_num(pose.c)}, "
        f"e1={_fmt_num(pose.e1)}, e2={_fmt_num(pose.e2)}, "
        f"e3={_fmt_num(pose.e3)})"
    )


def _format_point(point):
    cfg = tuple(getattr(point, "cfg", (0, 0, 0, 0)))
    uf = getattr(point, "uf", 0)
    tf = getattr(point, "tf", 0)
    return f"x5.Point(pose={_format_pose(point.pose)}, uf={uf}, tf={tf}, cfg={cfg})"


def _print_arm_state(name, handle):
    joint = x5.get_cjoint(handle)
    point = x5.get_cpoint(handle)
    print(f"{name}_JOINT = {_format_joint(joint)}")
    print(f"{name}_POSE = {_format_pose(point.pose)}")
    print(f"{name}_POINT = {_format_point(point)}")


def print_current_arm_state():
    handle_l_now = globals().get("handle_l")
    handle_r_now = globals().get("handle_r")
    if handle_l_now is None or handle_r_now is None:
        print("[debug] Arm handles are not ready yet.")
        return

    print("\n[debug] Current arm data:")
    for name, handle in (("LEFT", handle_l_now), ("RIGHT", handle_r_now)):
        try:
            _print_arm_state(name, handle)
        except Exception as exc:
            print(f"[debug] Failed to read {name} arm data: {exc}")


def _read_debug_key():
    try:
        import msvcrt
    except ImportError:
        value = input().strip().lower()
        return "enter" if value == "" else value[0]

    while True:
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue
        if key == "\r":
            return "enter"
        if key == "\x03":
            raise KeyboardInterrupt
        return key.lower()


def run_debug_step(title, code_text, action):
    global DEBUG_STEP_INDEX

    if not DEBUG_STEP_MODE:
        return action()

    DEBUG_STEP_INDEX += 1
    print(f"\n[DEBUG STEP {DEBUG_STEP_INDEX}] {title}")
    print("[CODE]")
    for line in code_text.strip().splitlines():
        print(f"    {line}")

    while True:
        print("[debug] Press Enter to run this step, or press p to print current arm data.", end="", flush=True)
        key = _read_debug_key()
        print()
        if key == "enter":
            break
        if key == "p":
            print_current_arm_state()
            continue
        print(f"[debug] Ignored key: {key!r}")

    result = action()
    print(f"[DEBUG STEP {DEBUG_STEP_INDEX} DONE] {title}")
    return result


def run_dual_movj(handle_l, handle_r, joint_l, joint_r, add_l, add_r, title, code_text, wait_complete=True):
    def _action():
        x5.movj(handle_r, joint_r, add_r)
        x5.movj(handle_l, joint_l, add_l)
        if wait_complete:
            x5.wait_move_done(handle_r)
            x5.wait_move_done(handle_l)

    return run_debug_step(title, code_text, _action)


def run_dual_movl(handle_l, handle_r, point_l, point_r, add_l, add_r, title, code_text, wait_complete=True):
    def _action():
        x5.movl(handle_l, point_l, add_l)
        x5.movl(handle_r, point_r, add_r)
        if wait_complete:
            x5.wait_move_done(handle_r)
            x5.wait_move_done(handle_l)

    return run_debug_step(title, code_text, _action)


def run_single_movl(handle, point, add_data, wait_handle, title, code_text, wait_complete=True):
    def _action():
        x5.movl(handle, point, add_data)
        if wait_complete:
            x5.wait_move_done(wait_handle)

    return run_debug_step(title, code_text, _action)


def run_right_movsj(handle_r, joint, data, title=None, code_text=None, wait_complete=True):
    if title is None:
        title = f"right arm movsj joint={joint}, data={data}"
    if code_text is None:
        code_text = f"x5.movsj(handle_r, {joint}, {data})"
        if wait_complete:
            code_text += "\nx5.wait_move_done(handle_r)"

    def _action():
        x5.movsj(handle_r, joint, data)
        if wait_complete:
            x5.wait_move_done(handle_r)

    return run_debug_step(title, code_text, _action)


def run_agv_step(title, code_text, action):
    return run_debug_step(f"AGV: {title}", code_text, action)

# 初始化左臂
INIT_POS_L = x5.Pose(x=250.328, y=-360.286, z=424.696, a=40.230, b=-8.049, c=-180-168.429, e1=0, e2=0, e3=0)
INIT_POINT_L = x5.Point(pose=INIT_POS_L, uf=0, tf=0, cfg=(0,0,0,7))
INIT_JOINT_L = x5.Joint(j1 = -65.576, j2 = -55.014, j3 = 21.534, j4 = -29.364, j5 = -82.855, j6 = -21.684, e1 = 70, e2 = 0, e3 = 0)
#JOINT_L = x5.Joint(j1 = -48.787, j2 = -35.166, j3 = 1.041, j4 = -45.555, j5 = -3.142, j6 = -22.880, e1 = 0, e2 = 0, e3 = 0)

# 初始化右臂
INIT_POS_R = x5.Pose(x=-197.361, y=-281.530, z=564.721, a=-2.166, b=0, c=-178.884, e1=17.891, e2=0, e3=200)
INIT_POINT_R = x5.Point(pose=INIT_POS_R, uf=0, tf=0, cfg=(0,0,0,7))
INIT_JOINT_R = x5.Joint(j1 = 53.805, j2 = -61.015, j3 = 20.265, j4 = -17.588, j5 = 51.496, j6 = -30.559, e1 = -66.526, e2 = 0, e3 = 10)

#目标1-夹物体
#POS_R = x5.Pose(x=-104.259, y=-79.354, z=380, a=84.673, b=21.038, c=94.316, e1=-125, e2=0, e3=265)

#JOINT_R1 = x5.Joint(j1 = 75.915, j2 = -21.823, j3 = 2.726, j4 = -31.314, j5 = 2.619, j6 = -14.891, e1 = -125, e2 = 0, e3 = 265)

#目标位置2
#POS_R = x5.Pose(x=-104.259, y=-79.354, z=380, a=84.673, b=21.038, c=94.316, e1=-125, e2=0, e3=265)
POS_R2 = x5.Pose(x=-127.816, y=-68.802, z=387.932, a=73.451, b=25.625, c=79.862, e1=-125, e2=0, e3=265)
POINT_R2 = x5.Point(pose=POS_R2, uf=0, tf=0, cfg=(0,0,0,7))


#左臂对称右臂的关节角度
def joint_left_be_right(joint_left,joint_right):
    
    joint_left.j1 = joint_right.j1
    joint_left.j2 = joint_right.j2
    joint_left.j3 = joint_right.j3
    joint_left.j4 = joint_right.j4
    joint_left.j5 = joint_right.j5
    joint_left.j6 = joint_right.j6
    joint_left.e1 = joint_right.e1
    print(f"左臂关节对称赋值完成，各关节值：")
    print(f"j1={joint_left.j1:.2f}, j2={joint_left.j2:.2f}, j3={joint_left.j3:.2f}")
    print(f"j4={joint_left.j4:.2f}, j5={joint_left.j5:.2f}, j6={joint_left.j6:.2f}, e1={joint_left.e1:.2f}")
    return joint_left

#左臂对称右臂的位姿态
def point_left_be_right(point_left,point_right):

    point_left.pose.x = point_right.pose.x
    point_left.pose.y = point_right.pose.y
    point_left.pose.z = point_right.pose.z
    point_left.pose.a = point_right.pose.a
    point_left.pose.b = point_right.pose.b
    point_left.pose.c = point_right.pose.c
    point_left.pose.e1 = point_right.pose.e1
    print(f"左臂位资对称赋值完成，位资值：")
    print(f"x={point_left.pose.x:.3f}, y={point_left.pose.y:.3f}, z={point_left.pose.z:.3f}")
    print(f"a={point_left.pose.a:.3f}, b={point_left.pose.b:.3f}, c={point_left.pose.c:.3f}, e1={point_left.pose.e1:.2f}")
    return point_left


def init_robot(handle_l, handle_r, add_data_1,add_data_2, SYSTEM_MODE):
    
    x5.set_system_mode(handle_l, SYSTEM_MODE)
    x5.set_system_mode(handle_r, SYSTEM_MODE)
    # 上使能
    x5.enable_servo(handle_l, 1)
    x5.enable_servo(handle_r, 1)

    time.sleep(1)
 
    #move_joint(handle_l, handle_r, add_data, INIT_JOINT_R)

def move_joint(handle_l, handle_r, add_data1,add_data2, joint_right):
    # 左臂对称
    joint_left = x5.Joint(0,0,0,0,0,0,0,0,15)
    joint_left = joint_left_be_right(joint_left,joint_right)

    run_dual_movj(
        handle_l,
        handle_r,
        joint_left,
        joint_right,
        add_data2,
        add_data1,
        "dual arm movj",
        f"x5.movj(handle_r, {_format_joint(joint_right)}, add_data1)\n"
        f"x5.movj(handle_l, {_format_joint(joint_left)}, add_data2)\n"
        "x5.wait_move_done(handle_r)\n"
        "x5.wait_move_done(handle_l)",
    )

#无等待
def move_joint_2(handle_l, handle_r, add_data1,add_data2, joint_right):
    joint_left = x5.Joint(0,0,0,0,0,0,0,0,0)
    joint_left = joint_left_be_right(joint_left,joint_right)

    run_dual_movj(
        handle_l,
        handle_r,
        joint_left,
        joint_right,
        add_data2,
        add_data1,
        "dual arm movj without wait",
        f"x5.movj(handle_r, {_format_joint(joint_right)}, add_data1)\n"
        f"x5.movj(handle_l, {_format_joint(joint_left)}, add_data2)",
        wait_complete=False,
    )
   
def move_point(handle_l, handle_r, add_data_1, add_data_2, point_right, wait_complete: bool = True):
    """
    控制机器人左右臂对称运动（整合无等待/等待完成逻辑）
    :param handle_l: 左臂句柄
    :param handle_r: 右臂句柄
    :param add_data_1: 右臂movj附加参数
    :param add_data_2: 左臂movj附加参数
    :param point_right: 右臂目标点
    :param wait_complete: 是否等待运动完成（True=等待，False=仅下发指令不等待）
    :return: None
    """
    # 左臂对称计算（原有重复逻辑提取）
    pose_left = x5.Pose(0,0,0,0,0,0,0,0,0)
    point_left = x5.Point(pose=pose_left, uf=0, tf=0, cfg=(0,0,0,7))
    point_left = point_left_be_right(point_left, point_right)

    # 下发运动指令（核心逻辑保留）
    def _action():
        x5.movj(handle_l, point_left, add_data_2)
        x5.movj(handle_r, point_right, add_data_1)
        if wait_complete:
            x5.wait_move_done(handle_r)
            x5.wait_move_done(handle_l)
            print(f"[运动完成] 左右臂已到达目标点（左臂对称于右臂）")
        else:
            print(f"[指令下发] 左右臂运动指令已下发，不等待执行完成")

    return run_debug_step(
        "dual arm point movj",
        f"x5.movj(handle_l, {_format_point(point_left)}, add_data_2)\n"
        f"x5.movj(handle_r, {_format_point(point_right)}, add_data_1)"
        + ("\nx5.wait_move_done(handle_r)\nx5.wait_move_done(handle_l)" if wait_complete else ""),
        _action,
    )

def move_point_2(handle_l, handle_r, add_data_1,add_data_2, point_right):
    # 左臂对称
    pose_left = x5.Pose(0,0,0,0,0,0,0,0,0)
    point_left = x5.Point(pose=pose_left, uf=0, tf=0, cfg=(0,0,0,7))
    point_left = point_left_be_right(point_left,point_right)

    
    run_dual_movl(
        handle_l,
        handle_r,
        point_left,
        point_right,
        add_data_2,
        add_data_1,
        "dual arm movl",
        f"x5.movl(handle_l, {_format_point(point_left)}, add_data_2)\n"
        f"x5.movl(handle_r, {_format_point(point_right)}, add_data_1)\n"
        "x5.wait_move_done(handle_r)\n"
        "x5.wait_move_done(handle_l)",
    )


def stop(handle_l, handle_r):
    x5.disconnect(handle_l)
    x5.disconnect(handle_r)

def AGV_Hands_1(target_lm: str):
   #到L1抓取点
    
    JOINT_R1 = x5.Joint(j1=-35.311, j2=-68.137, j3=8.781, j4=-26.162, j5=-101.035, j6=-59.148, e1=96.896, e2=0.000, e3=220.000)
    move_joint(handle_l, handle_r, x5.MovPointAdd(vel=100),x5.MovPointAdd(vel=100), JOINT_R1)
    
    if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_l).enable == 1):
        run_agv_step(
            f"{target_lm}: navigate to LM1",
            'agv.advanced_navigation_process(robot,"LM1",max_speed=0.5,max_wspeed=1,duration=0)',
            lambda: agv.advanced_navigation_process(robot,"LM1",max_speed=0.5,max_wspeed=1,duration=0),
        )
    
    run_right_movsj(handle_r, 8, 167)
    
    #抓取
    POS_R1 = x5.Pose(x=12.025, y=-450.750, z=435.024, a=0.113, b=-0.432, c=-1.599, e1=-12.646, e2=0.001, e3=167.000)
    POINT_R1 = x5.Point(pose=POS_R1, uf=0, tf=0, cfg=(0,0,0,7))
    POS_L1 = x5.Pose(x=16.315, y=-439.986, z=435.065, a=2.476, b=1.324, c=-0.630, e1=8.278, e2=0.001, e3=15.000)
    POINT_L1 = x5.Point(pose=POS_L1, uf=0, tf=0, cfg=(0,0,0,7))
    
    run_dual_movl(
        handle_l,
        handle_r,
        POINT_L1,
        POINT_R1,
        x5.MovPointAdd(vel=100),
        x5.MovPointAdd(vel=100),
        f"{target_lm}: dual arm grab pose",
        f"x5.movl(handle_l, {_format_point(POINT_L1)}, x5.MovPointAdd(vel=100))\n"
        f"x5.movl(handle_r, {_format_point(POINT_R1)}, x5.MovPointAdd(vel=100))\n"
        "x5.wait_move_done(handle_r)\n"
        "x5.wait_move_done(handle_l)",
    )
    
    run_right_movsj(handle_r, 8, 280)
    #time.sleep(2)
    #到达LM3
    if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_r).enable == 1):
        if(target_lm == "LM4" or target_lm == "LM5" or target_lm == "LM6"
           or target_lm == "LM4_2" or target_lm == "LM5_2" or target_lm == "LM6_2"
           or target_lm == "LM4_3" or target_lm == "LM5_3" or target_lm == "LM6_3"):
            run_agv_step(
                f"{target_lm}: navigate backward to LM3",
                'agv.advanced_navigation_process(robot,"LM3",method="backward",max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None)',
                lambda: agv.advanced_navigation_process(robot,"LM3",method='backward',max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None),
            )
        if(target_lm == "LM7" or target_lm == "LM8" or target_lm == "LM9"
           or target_lm == "LM7_2" or target_lm == "LM8_2" or target_lm == "LM9_2"
           or target_lm == "LM7_3" or target_lm == "LM8_3" or target_lm == "LM9_3"):
            run_agv_step(
                f"{target_lm}: navigate backward to LM10",
                'agv.advanced_navigation_process(robot,"LM10",method="backward",max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None)',
                lambda: agv.advanced_navigation_process(robot,"LM10",method='backward',max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None),
            )
    #到达左列1

    if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_r).enable == 1):
        if(target_lm == "LM4" or target_lm == "LM5" or target_lm == "LM6"
           or target_lm == "LM7" or target_lm == "LM8" or target_lm == "LM9"):
            high = -5
        if(target_lm == "LM4_2" or target_lm == "LM5_2" or target_lm == "LM6_2"
           or target_lm == "LM7_2" or target_lm == "LM8_2" or target_lm == "LM9_2"):
            high = -5 + 215
        if(target_lm == "LM4_3" or target_lm == "LM5_3" or target_lm == "LM6_3"
           or target_lm == "LM7_3" or target_lm == "LM8_3" or target_lm == "LM9_3"):
            high = -5 + 430
        
        run_right_movsj(
            handle_r,
            8,
            high,
            title=f"{target_lm}: right arm height movsj joint=8",
            code_text="x5.movsj(handle_r, 8, high)\nx5.wait_move_done(handle_r)",
        )
        if(target_lm == "LM4" or target_lm == "LM4_2" or target_lm == "LM4_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM4 without wait",
                'agv.advanced_navigation_process(robot,"LM4",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM4",max_speed=1,max_wspeed=1,duration=0),
            )
        if(target_lm == "LM5" or target_lm == "LM5_2" or target_lm == "LM5_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM5 without wait",
                'agv.advanced_navigation_process(robot,"LM5",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM5",max_speed=1,max_wspeed=1,duration=0),
            )
        if(target_lm == "LM6" or target_lm == "LM6_2" or target_lm == "LM6_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM6 without wait",
                'agv.advanced_navigation_process(robot,"LM6",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM6",max_speed=1,max_wspeed=1,duration=0),
            )
        if(target_lm == "LM7" or target_lm == "LM7_2" or target_lm == "LM7_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM7 without wait",
                'agv.advanced_navigation_process(robot,"LM7",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM7",max_speed=1,max_wspeed=1,duration=0),
            )
        if(target_lm == "LM8" or target_lm == "LM8_2" or target_lm == "LM8_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM8 without wait",
                'agv.advanced_navigation_process(robot,"LM8",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM8",max_speed=1,max_wspeed=1,duration=0),
            )
        if(target_lm == "LM9" or target_lm == "LM9_2" or target_lm == "LM9_3"):
            run_agv_step(
                f"{target_lm}: navigate to LM9 without wait",
                'agv.advanced_navigation_process(robot,"LM9",max_speed=1,max_wspeed=1,duration=0)',
                lambda: agv.advanced_navigation_process(robot,"LM9",max_speed=1,max_wspeed=1,duration=0),
            )
        
        
    else: stop(handle_l, handle_r)
    
    #80%
    
    POS_R2 = x5.Pose(x=12.059, y=110.572, z=616.797, a=-56.085, b=-0.190, c=0.369, e1=-12.646, e2=58.322, e3=-5)
    POINT_R2 = x5.Point(pose=POS_R2 , uf=0, tf=0, cfg=(0,0,0,7))
    POS_L2 = x5.Pose(x=16.362, y=117.128, z=603.427, a=-56.464, b=-0.832, c=1.685, e1=8.279, e2=0.000, e3=15.000)
    POINT_L2 = x5.Point(pose=POS_L2, uf=0, tf=0, cfg=(0,0,0,7))
    run_dual_movl(
        handle_l,
        handle_r,
        POINT_L2,
        POINT_R2,
        x5.MovPointAdd(vel=100,acc=39),#左臂速度
        x5.MovPointAdd(vel=100),#右臂速度
        f"{target_lm}: dual arm place pose",
        f"x5.movl(handle_l, {_format_point(POINT_L2)}, x5.MovPointAdd(vel=100,acc=39))\n"
        f"x5.movl(handle_r, {_format_point(POINT_R2)}, x5.MovPointAdd(vel=100))\n"
        "x5.wait_move_done(handle_r)\n"
        "x5.wait_move_done(handle_l)",
    )
    
    time.sleep(2)
    #松开物体
    if(target_lm == "LM4" or target_lm == "LM5" or target_lm == "LM6"
           or target_lm == "LM4_2" or target_lm == "LM5_2" or target_lm == "LM6_2"
           or target_lm == "LM4_3" or target_lm == "LM5_3" or target_lm == "LM6_3"):
        
        POINT_R2.pose.x = 40
        POINT_L2.pose.x = 40
        #move_point(handle_l, handle_r, x5.MovPointAdd(vel=100),x5.MovPointAdd(vel=100), POINT_R2)  
        run_dual_movl(
            handle_l,
            handle_r,
            POINT_L2,
            POINT_R2,
            x5.MovPointAdd(vel=100),
            x5.MovPointAdd(vel=100),
            f"{target_lm}: release object dual arm movl",
            f"x5.movl(handle_l, {_format_point(POINT_L2)}, x5.MovPointAdd(vel=100))\n"
            f"x5.movl(handle_r, {_format_point(POINT_R2)}, x5.MovPointAdd(vel=100))\n"
            "x5.wait_move_done(handle_r)\n"
            "x5.wait_move_done(handle_l)",
        )

        run_right_movsj(
            handle_r,
            7,
            0,
            title=f"{target_lm}: right arm waist movsj joint=7",
        )

        

        JOINT_R1 = x5.Joint(j1=-35.311, j2=-68.137, j3=8.781, j4=-26.162, j5=-101.035, j6=-59.148, e1=96.896, e2=0.000, e3=220.000)
        #move_joint(handle_l, handle_r, x5.MovPointAdd(vel=100),x5.MovPointAdd(vel=100), JOINT_R1)
        joint_left = x5.Joint(0,0,0,0,0,0,0,0,15)
        joint_left = joint_left_be_right(joint_left,JOINT_R1)
        run_dual_movj(
            handle_l,
            handle_r,
            joint_left,
            JOINT_R1,
            x5.MovPointAdd(vel=100),
            x5.MovPointAdd(vel=100),
            f"{target_lm}: dual arm return posture",
            f"x5.movj(handle_r, {_format_joint(JOINT_R1)}, x5.MovPointAdd(vel=100))\n"
            f"x5.movj(handle_l, {_format_joint(joint_left)}, x5.MovPointAdd(vel=100))",
            wait_complete=False,
        )
        
        if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_r).enable == 1):
            run_agv_step(
                f"{target_lm}: navigate backward to LM3 after release",
                'agv.advanced_navigation_process(robot,"LM3",method="backward",max_speed=2,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None)',
                lambda: agv.advanced_navigation_process(robot,"LM3",method='backward',max_speed=2,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None),
            )
            x5.wait_move_done(handle_r)
            x5.wait_move_done(handle_l)
        

   
    if(target_lm == "LM7" or target_lm == "LM8" or target_lm == "LM9"
           or target_lm == "LM7_2" or target_lm == "LM8_2" or target_lm == "LM9_2"
           or target_lm == "LM7_3" or target_lm == "LM8_3" or target_lm == "LM9_3"):
        POINT_L2.pose.x = 40
        run_single_movl(
            handle_l,
            POINT_L2,
            x5.MovPointAdd(vel=100),
            handle_l,
            f"{target_lm}: left arm release x movl",
            f"x5.movl(handle_l, {_format_point(POINT_L2)}, x5.MovPointAdd(vel=100))\n"
            "x5.wait_move_done(handle_l)",
        )
        POS_L2 = x5.Pose(x=40.257, y=256.428, z=434.430, a=-56.464, b=-0.832, c=1.685, e1=8.279, e2=0.000, e3=15.000)
        POINT_L2 = x5.Point(pose=POS_L2, uf=0, tf=0, cfg=(0,0,0,7))
        run_single_movl(
            handle_l,
            POINT_L2,
            x5.MovPointAdd(vel=100),
            handle_l,
            f"{target_lm}: left arm lower movl without wait",
            f"x5.movl(handle_l, {_format_point(POINT_L2)}, x5.MovPointAdd(vel=100))",
            wait_complete=False,
        )
        #x5.wait_move_done(handle_l)
        run_agv_step(
            f"{target_lm}: translate AGV left",
            "agv.agv_translate_process(robot,0.19,0,0.2,0)",
            lambda: agv.agv_translate_process(robot,0.19,0,0.2,0),
        )
        POINT_R2.pose.x = 40
        run_single_movl(
            handle_r,
            POINT_R2,
            x5.MovPointAdd(vel=100),
            handle_r,
            f"{target_lm}: right arm release movl",
            f"x5.movl(handle_r, {_format_point(POINT_R2)}, x5.MovPointAdd(vel=100))\n"
            "x5.wait_move_done(handle_r)",
        )
        run_right_movsj(
            handle_r,
            7,
            0,
            title=f"{target_lm}: right arm waist movsj joint=7",
            wait_complete=False,
        )

        run_agv_step(
            f"{target_lm}: translate AGV right",
            "agv.agv_translate_process(robot,0.19,0,-0.2,0)",
            lambda: agv.agv_translate_process(robot,0.19,0,-0.2,0),
        )
        x5.wait_move_done(handle_r)
        JOINT_R1 = x5.Joint(j1=-35.311, j2=-68.137, j3=8.781, j4=-26.162, j5=-101.035, j6=-59.148, e1=96.896, e2=0.000, e3=220.000)
        #move_joint(handle_l, handle_r, x5.MovPointAdd(vel=100),x5.MovPointAdd(vel=100), JOINT_R1)
        joint_left = x5.Joint(0,0,0,0,0,0,0,0,15)
        joint_left = joint_left_be_right(joint_left,JOINT_R1)
        run_dual_movj(
            handle_l,
            handle_r,
            joint_left,
            JOINT_R1,
            x5.MovPointAdd(vel=70),
            x5.MovPointAdd(vel=100),
            f"{target_lm}: dual arm return posture",
            f"x5.movj(handle_r, {_format_joint(JOINT_R1)}, x5.MovPointAdd(vel=100))\n"
            f"x5.movj(handle_l, {_format_joint(joint_left)}, x5.MovPointAdd(vel=70))",
            wait_complete=False,
        )
        if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_r).enable == 1):
            run_agv_step(
                f"{target_lm}: navigate backward to LM10 after release",
                'agv.advanced_navigation_process(robot,"LM10",method="backward",max_speed=2,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None)',
                lambda: agv.advanced_navigation_process(robot,"LM10",method='backward',max_speed=2,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None),
            )
            x5.wait_move_done(handle_r)
            x5.wait_move_done(handle_l)
    
    
if __name__ == "__main__":
    robot = agv.md.RobotManager.create_with_workers()    # 创建机器人对象
    robot.connect('192.168.1.52')    # 连接机器人
    robot.navigation_worker      # 获取导航控制器

    x5.enable_debug_output(True)    # 开启X5 SDK调试输出，便于查看日志信息
    # 创建TCP连接
    handle_l = x5.connect("192.168.1.9")    # 根据实际情况替换为左臂控制器的IP地址
    handle_r = x5.connect("192.168.1.10")   # 根据实际情况替换为右臂控制器的IP地址

    # 初始化
    x5.reset(handle_l)    # 重置左臂控制器
    x5.reset(handle_r)    # 重置右臂控制器
    #time.sleep(3)  # 等待控制器重置完成
    x5.set_speed(handle_l,100)  # 设置左臂运动速度为100mm/s
    x5.set_speed(handle_r,100)      # 设置右臂运动速度为100mm/s
    add_data_1 = x5.MovPointAdd(vel=100)    #设置右臂movj附加参数，速度为100mm/s
    add_data_2 = x5.MovPointAdd(vel=100)    #设置左臂movj附加参数，速度为100mm/s
    init_robot(handle_l, handle_r, add_data_1,add_data_2, x5.SYSTEM_MODE_MANUAL)    # 初始化机器人，设置为手动模式
    
    #####################初始位置###########################
    
    #初始手臂点位
    run_right_movsj(
        handle_r,
        7,
        0,
        title="initial right arm waist movsj joint=7",
    )    # 右臂回到初始位置


    JOINT_R = x5.Joint(j1 = -4.916, j2 = -70.886, j3 = -13.438, j4 = -8.955, j5 = -51.265, j6 = -30.629, e1 = 
                       64.060, e2 = 0, e3 = 200)
    move_joint(handle_l, handle_r, x5.MovPointAdd(vel=100),x5.MovPointAdd(vel=100), JOINT_R)    # 右臂移动到目标位置，左臂对称移动
    #到L2起点
    if(x5.get_system_state(handle_l).enable == 1 and x5.get_system_state(handle_r).enable == 1):
        run_agv_step(
            "navigate to LM2",
            'agv.advanced_navigation_process(robot,"LM2",max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None)',
            lambda: agv.advanced_navigation_process(robot,"LM2",max_speed=1,max_wspeed=1,duration=0,reach_dist=None,reach_angle=None),
        )
    
    AGV_Hands_1("LM4")
    
    AGV_Hands_1("LM5")
    AGV_Hands_1("LM6")
    AGV_Hands_1("LM7")
    AGV_Hands_1("LM8")
    AGV_Hands_1("LM9")
    '''
    AGV_Hands_1("LM4_2")
    AGV_Hands_1("LM5_2")
    AGV_Hands_1("LM6_2")
    AGV_Hands_1("LM7_2")
    AGV_Hands_1("LM8_2")
    AGV_Hands_1("LM9_2")
    
    AGV_Hands_1("LM4_3")
    AGV_Hands_1("LM5_3")
    AGV_Hands_1("LM6_3")
    AGV_Hands_1("LM7_3")
    AGV_Hands_1("LM8_3")
    AGV_Hands_1("LM9_3")
    '''
    stop(handle_l, handle_r)

   
