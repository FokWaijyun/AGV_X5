import time
import threading
from copy import deepcopy
from typing import Any, Callable

import xapi.api as x5


# ==================== 配置 ====================
# 双臂 ip
left_arm_ip = "192.168.1.9"
right_arm_ip = "192.168.1.10"

SPEED = 20
TIMEOUT_S = 1000.0
PALLET_ROWS = 2
PALLET_COLS = 2
START_DI_INDEX = 2
START_DO_INDEX = 2
START_POLL_INTERVAL_S = 0.05
PLACE_HEIGHT = 150.0  # Approach height above each pallet position (mm).

# 双臂句柄号
handle_l = x5.connect(left_arm_ip)    # 左臂控制器的IP地址
handle_r = x5.connect(right_arm_ip)   # 右臂控制器的IP地址


# ==================== 工具函数（来自 single_move.py） ====================
def wait_cmd_sent(handle: int) -> None:
    """等命令发送完成，失败不中断"""
    try:
        x5.wait_cmd_send_done(handle)
    except Exception:
        pass


def wait_state(
    handle: int,
    predicate: Callable[[Any], bool],
    *,
    timeout_s: float,
    desc: str,
) -> Any:
    """轮询等待系统状态满足条件"""
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    last_state = None
    while time.monotonic() < deadline:
        last_state = x5.get_system_state(handle)
        if predicate(last_state):
            return last_state
        time.sleep(0.1)
    raise RuntimeError(f"等待 {desc} 超时；最后状态={last_state}")


class SignalMonitor:
    """复用右臂连接持续监测 DI2，避免运动等待阻塞信号轮询。"""

    def __init__(self, handle: int):
        self.handle = handle
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.run, name="di2-do2-monitor")

    def run(self):
        try:
            last_state = None
            while not self.stop_event.is_set():
                state = int(x5.get_di(self.handle, START_DI_INDEX))
                if state != last_state:
                    self.ready.clear()
                    # 检测到低电平后立即下发 DO2=0。
                    x5.set_do(self.handle, START_DO_INDEX, state)
                    try:
                        x5.wait_set_do_done(self.handle, 1000)
                    except AttributeError:
                        x5.wait_cmd_send_done(self.handle)
                    last_state = state
                    if state == 1:
                        self.ready.set()
                self.stop_event.wait(START_POLL_INTERVAL_S)
        except Exception as exc:
            self.error = exc
            self.ready.clear()
            print(f"[信号监测失败] {exc}")
            try:
                x5.set_do(self.handle, START_DO_INDEX, 0)
            except Exception:
                pass

    def wait_start(self):
        print("[启动] 等待右臂 DI2=1、DO2=1")
        while True:
            if self.error is not None:
                raise RuntimeError("DI2/DO2 监测失败") from self.error
            if self.ready.wait(START_POLL_INTERVAL_S):
                return

    def close(self):
        self.stop_event.set()
        if self.thread.ident is not None:
            self.thread.join()


def print_state(handle: int, label: str) -> Any:
    """打印当前状态"""
    state = x5.get_system_state(handle)
    print(
        f"[{label}] alarm={getattr(state, 'alarm', '?')} "
        f"run={getattr(state, 'run', '?')} "
        f"enable={getattr(state, 'enable', '?')} "
        f"mode={getattr(state, 'mode', '?')} "
        f"remote={getattr(state, 'remote', '?')}"
    )
    return state


# ==================== 准备（来自 single_move.py 的 prepare） ====================
def prepare(handle: int, label: str, timeout_s: float = TIMEOUT_S) -> None:
    """把机器人准备到可发运动的状态"""
    print_state(handle, f"{label} 初始")

    # 1. 复位报警
    print(f"[{label}] 复位报警 ...")
    try:
        x5.reset(handle)
        wait_cmd_sent(handle)
    except Exception as exc:
        print(f"[{label}] 复位报警警告: {exc}")

    state = x5.get_system_state(handle)
    if int(getattr(state, "alarm", 0)) > 0:
        state = wait_state(
            handle,
            lambda s: int(getattr(s, "alarm", 0)) == 0,
            timeout_s=timeout_s,
            desc=f"{label} 报警清除",
        )

    # 2. 如果还在运行，先停
    if int(getattr(state, "run", 3)) != 3:
        print(f"[{label}] 停止当前运动 ...")
        x5.abort(handle)
        try:
            x5.wait_move_done(handle, int(timeout_s * 1000))
        except TypeError:
            x5.wait_move_done(handle)
        state = wait_state(
            handle,
            lambda s: int(getattr(s, "run", 3)) == 3,
            timeout_s=timeout_s,
            desc=f"{label} 运动停止",
        )

    # 3. 切【本地】模式（AUTOCMD 必须配本地）
    if int(getattr(state, "remote", 0)) != 0:
        print(f"[{label}] 切换到本地模式 ...")
        x5.set_remote(handle, False)
        wait_cmd_sent(handle)
        state = wait_state(
            handle,
            lambda s: int(getattr(s, "remote", 0)) == 0,
            timeout_s=timeout_s,
            desc=f"{label} 本地模式",
        )

    # 4. 切自动命令模式
    if int(getattr(state, "mode", 0)) != int(x5.SYSTEM_MODE_AUTOCMD):
        print(f"[{label}] 切换到 AUTOCMD 模式 ...")
        x5.set_system_mode(handle, x5.SYSTEM_MODE_AUTOCMD)
        wait_cmd_sent(handle)
        state = wait_state(
            handle,
            lambda s: int(getattr(s, "mode", 0)) == int(x5.SYSTEM_MODE_AUTOCMD),
            timeout_s=timeout_s,
            desc=f"{label} AUTOCMD 模式",
        )

    # 5. 上使能
    if int(getattr(state, "enable", 0)) != 1:
        print(f"[{label}] 上使能 ...")
        x5.enable_servo(handle, True)
        wait_cmd_sent(handle)
        state = wait_state(
            handle,
            lambda s: int(getattr(s, "enable", 0)) == 1,
            timeout_s=timeout_s,
            desc=f"{label} 上使能",
        )

    # 6. 设速度
    x5.set_speed(handle, SPEED)
    wait_cmd_sent(handle)

    print_state(handle, f"{label} 就绪")


# ==================== 点位 ====================
def build_pallet_positions(handle):
    """Build a 2 x 2 pallet: PR[7]=start, PR[8]=row end, PR[9]=column end.



    """
    start = x5.get_pr(handle, 7)
    row_end = x5.get_pr(handle, 8)
    col_end = x5.get_pr(handle, 9)
    if any((p.uf, p.tf) != (start.uf, start.tf) for p in (row_end, col_end)):
        raise ValueError("Pallet PR[7:9] must use the same user/tool frames")

    positions = []
    for row in range(PALLET_ROWS):
        for col in range(PALLET_COLS):
            place = deepcopy(start)
            for axis in ("x", "y", "z"):
                origin = getattr(start.pose, axis)
                value = (
                    origin
                    + row * (getattr(row_end.pose, axis) - origin) / (PALLET_ROWS - 1)
                    + col * (getattr(col_end.pose, axis) - origin) / (PALLET_COLS - 1)
                )
                setattr(place.pose, axis, value)
            prep_pal = deepcopy(place)
            prep_pal.pose.z += PLACE_HEIGHT
            positions.append({"place": place, "prep_pal": prep_pal})
    return positions


# Pallet placement; keep the right-arm handoff positions fixed.
Pallet_POS_l = build_pallet_positions(handle_l)

Place_POS_l = {
    "prep_pal": x5.get_pr(handle_l, 3),  # ???????/?????
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


# ==================== 运动封装 ====================
def run_dual_movj(handle_l, handle_r, point_l, point_r, timeout_ms: int):
    """双臂同时运动到指定点位，并等待各自完成"""
    x5.movj(handle_r, point_r)
    x5.movj(handle_l, point_l)

    try:
        x5.wait_move_done(handle_r, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_r)
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)


def init_dual_arm():
    """初始化双臂——改用 single_move.py 的 prepare，逐步等待状态到位"""
    prepare(handle_l, "左臂")
    prepare(handle_r, "右臂")

    # 双臂同时运动到 Start 点位
    run_dual_movj(
        handle_l, handle_r,
        Pick_POS_l["Start"], Pick_POS_r["Start"],
        int(TIMEOUT_S * 1000),
    )

    time.sleep(1)  # 保持原有节奏


# ==================== 右臂动作 ====================
def right_arm_pick_and_place():
    timeout_ms = int(TIMEOUT_S * 1000)

    x5.movj(handle_r, Pick_POS_r["prep_pick"])
    x5.movj(handle_r, Pick_POS_r["grab"])
    try:
        x5.wait_move_done(handle_r, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_r)

    x5.set_do(handle_r, 0, 1)  # 右臂吸气
    time.sleep(1)

    x5.movj(handle_r, Pick_POS_r["prep_pick"])
    x5.movj(handle_r, Place_POS_r["prep_pal"])
    try:
        x5.wait_move_done(handle_r, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_r)

    x5.movj(handle_r, Place_POS_r["place"])
    try:
        x5.wait_move_done(handle_r, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_r)

    time.sleep(0.5)
    # 右臂最后状态是吸气，吹气由左臂流程控制，等左臂吹气完成后再关右臂吸气


# ==================== 左臂动作 ====================
def left_arm_pick_and_place(place_pos):
    timeout_ms = int(TIMEOUT_S * 1000)

    x5.movj(handle_l, Pick_POS_l["prep_pick"])
    x5.movj(handle_l, Pick_POS_l["grab"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)

    # 左右臂交接动作
    x5.set_do(handle_l, 0, 1)  # 左臂吸气
    time.sleep(0.5)
    x5.set_do(handle_r, 0, 0)  # 右臂吸气 关闭
    x5.set_do(handle_r, 1, 1)  # 右臂吹气
    time.sleep(0.5)
    x5.set_do(handle_r, 1, 0)  # ??????

    # ?????????? PR[4] ??????????????
    x5.movj(handle_r, Pick_POS_r["Start"])
    try:
        x5.wait_move_done(handle_r, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_r)

    # ???????? PR[3]?????????????
    x5.movj(handle_l, Place_POS_l["prep_pal"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)

    x5.movj(handle_l, place_pos["prep_pal"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)

    # Pallet placement; keep the right-arm handoff positions fixed.
    x5.movl(handle_l, place_pos["place"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)

    x5.set_do(handle_l, 0, 0)  # 左臂吸气关闭
    x5.set_do(handle_l, 1, 1)  # 左臂吹气
    time.sleep(0.5)
    x5.set_do(handle_l, 1, 0)
    x5.movl(handle_l, place_pos["prep_pal"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)

    # 每轮放料后，左臂回到 PR[4] 开始点并等待到位。
    x5.movj(handle_l, Pick_POS_l["Start"])
    try:
        x5.wait_move_done(handle_l, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle_l)



# ==================== 主流程 ====================
def main():
    x5.enable_debug_output(True)
    signal_monitor = SignalMonitor(handle_r)
    try:
        signal_monitor.thread.start()
        signal_monitor.wait_start()
        init_dual_arm()
        # Pallet placement; keep the right-arm handoff positions fixed.
        for index, place_pos in enumerate(Pallet_POS_l):
            row, col = divmod(index, PALLET_COLS)
            print(f"[Pallet] row={row + 1}, col={col + 1}")
            signal_monitor.wait_start()
            right_arm_pick_and_place()
            left_arm_pick_and_place(place_pos)
    except x5.RobException as rex:
        print(f"\n[错误] 接口: {rex.api_name}")
        print(f"[错误] 代码: {rex.error_code}")
        print(f"[错误] 内容: {rex.error_message}")
    except Exception as exc:
        print(f"\n[错误] {exc}")
    finally:
        signal_monitor.close()
        for label, handle in (("左臂", handle_l), ("右臂", handle_r)):
            try:
                x5.enable_servo(handle, False)
                wait_cmd_sent(handle)
                print(f"[清理] {label} 下使能完成")
            except Exception as exc:
                print(f"[清理] {label} 下使能警告: {exc}")
            try:
                x5.disconnect(handle)
                print(f"[清理] {label} 已断开连接")
            except Exception as exc:
                print(f"[清理] {label} 断开警告: {exc}")
        try:
            x5.logger_shutdown()
        except Exception:
            pass
        print("[主流程] 程序结束")


if __name__ == "__main__":
    main()
