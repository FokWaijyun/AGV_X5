import time
from copy import deepcopy

import xapi.api as x5

"""场景描述：双臂物料搬运示例程序
设备：双臂机械臂，左臂用于放料，右臂用于取料，右臂取料后交给左臂，左臂将物料放入托盘中；
    一条传送带，传送带上有物料，一个传感器 DI（遇到物体会输出高电平信号）；
    右手句柄号的 DO2 用于输出信号给传送带，控制传送带的启停；
"""


# 双臂 IP
left_arm_ip = "192.168.1.9"
right_arm_ip = "192.168.1.10"

SPEED = 20

PALLET_ROWS = 2
PALLET_COLS = 2
PLACE_HEIGHT = 150.0

START_DI_INDEX = 2
START_DO_INDEX = 2
SIGNAL_POLL_INTERVAL_S = 0.05


def build_pallet_positions(handle): # 
    """用 PR7、PR8、PR9 生成左臂 2×2 托盘点位。
    目前码垛的写法无法支持单行或单列，会除零"""
    start = x5.get_pr(handle, 7)
    row_end = x5.get_pr(handle, 8)
    col_end = x5.get_pr(handle, 9)

    positions = []
    for row in range(PALLET_ROWS):
        for col in range(PALLET_COLS):
            place = deepcopy(start)
            for axis in ("x", "y", "z"):
                start_value = getattr(start.pose, axis)
                row_offset = getattr(row_end.pose, axis) - start_value
                col_offset = getattr(col_end.pose, axis) - start_value
                value = (
                    start_value
                    + row * row_offset / max(1, PALLET_ROWS - 1)
                    + col * col_offset / max(1, PALLET_COLS - 1)
                )
                setattr(place.pose, axis, value)

            prep_pal = deepcopy(place)
            prep_pal.pose.z += PLACE_HEIGHT
            positions.append({"place": place, "prep_pal": prep_pal})
    
    return positions # 一维列表，包含码垛所有的点位


def MoveJ(handle, point):
    """关节运动到指定点位。"""
    x5.movj(handle, point)
    x5.wait_move_done(handle)

def MoveL(handle, point):
    """直线运动到指定点位。"""
    x5.movl(handle, point)
    x5.wait_move_done(handle)


def run_dual_movj(handle_l, handle_r, point_l, point_r):
    """双臂同时关节运动到指定点位。"""
    x5.movj(handle_r, point_r)
    x5.movj(handle_l, point_l)
    
    x5.wait_move_done(handle_r)
    x5.wait_move_done(handle_l)


def init_dual_arm(handle_l, handle_r, point_l, point_r, speed=SPEED):
    """初始化双臂并回到开始点。双臂句柄，左臂点位，右臂点位，速度。"""
    x5.reset(handle_l)
    x5.reset(handle_r)
    x5.abort(handle_l)
    x5.abort(handle_r)

    x5.set_remote(handle_l, False)
    x5.set_remote(handle_r, False)
    x5.set_system_mode(handle_l, x5.SYSTEM_MODE_AUTOCMD)
    x5.set_system_mode(handle_r, x5.SYSTEM_MODE_AUTOCMD)

    x5.enable_servo(handle_l, True)
    x5.enable_servo(handle_r, True)
    x5.set_speed(handle_l, speed)
    x5.set_speed(handle_r, speed)

    run_dual_movj(handle_l, handle_r, point_l, point_r)
    time.sleep(1)


def right_arm_pick_and_place(handle, pick_pos, place_pos):
    """右臂取料并移动到交接位置。"""
    MoveJ(handle, pick_pos["prep_pick"])
    MoveJ(handle, pick_pos["grab"])

    x5.set_do(handle, 0, 1)
    time.sleep(1)

    MoveJ(handle, pick_pos["prep_pick"])
    MoveJ(handle, place_pos["prep_pal"])
    MoveJ(handle, place_pos["place"])
    time.sleep(0.5)


def left_arm_pick_and_place(handle_l, handle_r, pick_pos_l, place_pos_l, pick_pos_r, pallet_pos):
    """左臂接料后放入一个托盘格。"""
    MoveJ(handle_l, pick_pos_l["prep_pick"])
    MoveJ(handle_l, pick_pos_l["grab"])

    # 双臂交接
    x5.set_do(handle_l, 0, 1)
    time.sleep(0.5)
    x5.set_do(handle_r, 0, 0)
    x5.set_do(handle_r, 1, 1)
    time.sleep(0.5)
    x5.set_do(handle_r, 1, 0)

    # 右臂避让，左臂再进入托盘区
    MoveJ(handle_r, pick_pos_r["Start"])

    MoveJ(handle_l, place_pos_l["prep_pal"])
    MoveJ(handle_l, pallet_pos["prep_pal"])
    MoveL(handle_l, pallet_pos["place"]) # 使用直线运动
    x5.set_do(handle_l, 0, 0)
    x5.set_do(handle_l, 1, 1)
    time.sleep(0.5)
    x5.set_do(handle_l, 1, 0)

    MoveL(handle_l, pallet_pos["prep_pal"]) # 使用直线运动
    MoveJ(handle_l, pick_pos_l["Start"])


def main():
    x5.enable_debug_output(True)
    try:
        # 双臂句柄号
        handle_l = x5.connect(left_arm_ip)
        handle_r = x5.connect(right_arm_ip)

        pick_pos_l = {
        "Start": x5.get_pr(handle_l, 4),
        "prep_pick": x5.get_pr(handle_l, 5),
        "grab": x5.get_pr(handle_l, 6),
        }
        place_pos_l = {
            "prep_pal": x5.get_pr(handle_l, 3),
        }
        pick_pos_r = {
            "Start": x5.get_pr(handle_r, 4),
            "prep_pick": x5.get_pr(handle_r, 5),
            "grab": x5.get_pr(handle_r, 6),
        }
        place_pos_r = {
            "place": x5.get_pr(handle_r, 2),
            "prep_pal": x5.get_pr(handle_r, 3),
        }

        pallet_positions = build_pallet_positions(handle_l)

        # 首次触发允许初始化和第一格动作；后续每格均要求新的低到高触发。
        init_dual_arm(handle_l, handle_r, 
                      pick_pos_l["Start"], pick_pos_r["Start"], speed=SPEED)

        for index, pallet_pos in enumerate(pallet_positions):
            row, col = divmod(index, PALLET_COLS)
            print(f"[托盘] 第 {row + 1} 行，第 {col + 1} 列")
            right_arm_pick_and_place(handle_r, pick_pos_r, place_pos_r)
            left_arm_pick_and_place(
                handle_l,
                handle_r,
                pick_pos_l,
                place_pos_l,
                pick_pos_r,
                pallet_pos,
            )

    except x5.RobException as error:
        print(f"[错误] 接口: {error.api_name}")
        print(f"[错误] 代码: {error.error_code}")
        print(f"[错误] 内容: {error.error_message}")
    except Exception as error:
        print(f"[错误] {error}")


if __name__ == "__main__":
    main()
