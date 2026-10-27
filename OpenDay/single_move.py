#!/usr/bin/env python3
"""同时连接左右臂，运动到指定初始位置。

关键点：
- AUTOCMD 模式配【本地模式】（set_remote(False)），否则上使能报 -603
- 左右臂独立连接、独立准备、独立运动
- 顺序：清报警 → 停运动 → 本地 → AUTOCMD → 上使能 → 运动
"""
from __future__ import annotations

import time
from typing import Any, Callable

import xapi.api as x5


# ==================== 配置 ====================
IP_LEFT = "192.168.1.9"        # 左臂 IP
IP_RIGHT = "192.168.1.10"      # 右臂 IP
SPEED = 5                     # 全局速度百分比
TIMEOUT_S = 10.0               # 状态等待超时（秒）

# 目标关节点位
LEFT_POSE = x5.Joint(
    j1=-70, j2=-85, j3=20, j4=-45, j5=2, j6=-30,
    e1=6, e2=0, e3=0,
)
RIGHT_POSE = x5.Joint(
    j1=80, j2=-80, j3=-40, j4=-40, j5=14, j6=-55,
    e1=86, e2=0, e3=0,
)


# ==================== 工具函数 ====================
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


# ==================== 准备 ====================
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


# ==================== 运动 ====================
def move_to(handle: int, label: str, target: x5.Joint, timeout_ms: int) -> None:
    """关节运动到目标位置"""
    print(f"[{label}] 运动到目标位置 ...")
    x5.movj(handle, target)
    try:
        x5.wait_move_done(handle, timeout_ms)
    except TypeError:
        x5.wait_move_done(handle)
    print(f"[{label}] 运动完成")


# ==================== 主流程 ====================
def main() -> None:
    hl = hr = None
    try:
        # 1. 连接左右臂
        print(f"[主流程] 连接左臂 {IP_LEFT} ...")
        hl = x5.connect(IP_LEFT)
        print(f"[主流程] 左臂句柄号: {hl}")

        print(f"[主流程] 连接右臂 {IP_RIGHT} ...")
        hr = x5.connect(IP_RIGHT)
        print(f"[主流程] 右臂句柄号: {hr}")

        # 2. 分别准备左右臂
        prepare(hl, "左臂")
        prepare(hr, "右臂")

        # 3. 分别运动到目标位置
        timeout_ms = int(TIMEOUT_S * 1000)
        move_to(hl, "左臂", LEFT_POSE, timeout_ms)
        move_to(hr, "右臂", RIGHT_POSE, timeout_ms)

        # 4. 读取确认
        joint_l = x5.get_cjoint(hl)
        joint_r = x5.get_cjoint(hr)
        print(f"[左臂] 当前关节: {joint_l}")
        print(f"[右臂] 当前关节: {joint_r}")

        print("[主流程] 完成")

    except x5.RobException as rex:
        print(f"\n[错误] 接口: {rex.api_name}")
        print(f"[错误] 代码: {rex.error_code}")
        print(f"[错误] 内容: {rex.error_message}")

    except Exception as exc:
        print(f"\n[错误] {exc}")

    finally:
        # 5. 下使能 + 断开
        for label, handle in (("左臂", hl), ("右臂", hr)):
            if handle is None:
                continue
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