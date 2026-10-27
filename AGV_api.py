"""
Group: api.py模块
Description: 机器人API示例模块
Date: 2025-03-20 (add at v1.0.0)
"""
import models as md
import time
import math  # 新增：导入数学模块用于角度转弧度

# AGV 查询点云投影图片流程（对应 1675/0x068B 接口）
def agv_cloud_projection_process(robot: md.RobotManager, req_type: str, file_name: str, points: list = None, wait_complete: bool = True):
    """
    AGV 查询当前识别相机的点云投影图片，支持获取图片和设置多边形两种模式
    :param robot: 机器人管理器实例
    :param req_type: 请求类型，"getImage"=获取点云图片，"setPoints"=设置多边形并返回图片
    :param file_name: 图片文件名，必填不可缺省
    :param points: 多边形各点坐标列表，仅 req_type="setPoints" 时必填
    :param wait_complete: 是否等待任务执行完成（True=等待完成，False=仅下发任务不等待）
    :return: 等待模式下：成功返回响应数据字典，失败返回None；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（严格匹配接口必填要求）
    if not isinstance(robot, md.RobotManager):
        print(f"[ERROR] robot参数必须为RobotManager实例，当前输入类型：{type(robot)}")
        return False if not wait_complete else None

    if req_type not in ["getImage", "setPoints"]:
        print(f"[ERROR] req_type必须为 'getImage' 或 'setPoints'，当前输入：{req_type}")
        return False if not wait_complete else None

    if not isinstance(file_name, str) or file_name.strip() == "":
        print(f"[ERROR] file_name必须为非空字符串，当前输入：{file_name}")
        return False if not wait_complete else None

    if req_type == "setPoints":
        if points is None or not isinstance(points, list) or len(points) == 0:
            print(f"[ERROR] setPoints模式下points必须为非空坐标列表，当前输入：{points}")
            return False if not wait_complete else None

    # 2. 构造请求数据（严格对应文档字段名）
    req_data = {
        "type": req_type,
        "fileName": file_name
    }
    if req_type == "setPoints":
        req_data["points"] = points

    # 3. 创建点云图片查询任务（action=1675 对应接口编号）
    cloud_task = md.Task.create_task(
        action=1675,
        data=req_data
    )

    # 下发任务（1675属于1000~2000区间，自动分配到state_worker）
    robot.state_worker.add_task(cloud_task)
    mode_desc = "获取点云图片" if req_type == "getImage" else "设置多边形并获取图片"
    print(f"[Cloud Projection] 已下发{mode_desc}指令 | 文件名={file_name} | 等待完成={wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # 等待模式：等待任务执行完成（复用现有wait_task_complete机制）
    wait_flag = robot.state_worker.wait_task_complete(cloud_task, timeout=5)

    # 4. 结果判断与日志输出
    if not wait_flag:
        print(f"[ERROR] 点云图片查询指令执行超时：{mode_desc}")
        return None

    if cloud_task.result is not None and isinstance(cloud_task.result, dict):
        task_status = cloud_task.result.get("task_status", -1)
        ret_code = cloud_task.result.get("ret_code", 0)
        err_msg = cloud_task.result.get("err_msg", "无错误信息")

        if task_status == 4:
            res_data = {
                "type": cloud_task.result.get("type"),
                "fileName": cloud_task.result.get("fileName"),
                "imageBase64": cloud_task.result.get("imageBase64"),
                "ret_code": ret_code
            }
            print(f"[SUCCESS] 点云图片查询完成：{mode_desc} | 文件名={file_name}")
            return res_data
        else:
            print(f"[FAILED] 点云图片查询失败：{mode_desc} | 状态码={task_status} | 错误码={ret_code} | 错误信息={err_msg} | 结果={cloud_task.result}")
            return None
    else:
        print(f"[FAILED] 点云图片查询结果异常：{mode_desc} | 结果={cloud_task.result}")
        return None

# AGV 获取机器人位置流程（对应 1020/0x3F8 接口）
def agv_get_pose_process(robot: md.RobotManager, wait_complete: bool = True):
    """
    AGV 获取当前位置姿态（坐标+角度）
    :param robot: 机器人管理器实例
    :param wait_complete: 是否等待位置查询任务执行完成（True=等待完成，False=仅下发任务不等待）
    :return: 等待模式下：成功返回位置字典，失败返回None；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（基础实例校验）
    if not isinstance(robot, md.RobotManager):
        print(f"[ERROR] robot参数必须为RobotManager实例，当前输入类型：{type(robot)}")
        return False if not wait_complete else None

    # 2. 创建获取位置任务（action=1020 对应位置查询接口）
    pose_task = md.Task.create_task(
        action=1020,
        data={"simple": True}  # simple模式返回精简位置信息
    )

    # 3. 下发任务（1020属于状态查询类，分配到state_worker）
    robot.state_worker.add_task(pose_task)
    print(f"[Get Pose] 已下发位置查询指令 | 等待完成={wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # 等待模式：等待任务执行完成（超时5秒）
    wait_flag = robot.state_worker.wait_task_complete(pose_task, timeout=5)

    # 4. 结果判断与日志输出
    if not wait_flag:
        print(f"[ERROR] 位置查询指令执行超时")
        return None

    # 检查任务结果有效性
    if pose_task.result is not None and isinstance(pose_task.result, dict):
        task_status = pose_task.result.get("task_status", -1)
        if task_status == 4:
            # 提取核心位置信息（x/y/angle 为通用位置字段，可根据实际接口调整）
            robot_pose = {
                "x": pose_task.result.get("x", 0.0),       # X坐标（米）
                "y": pose_task.result.get("y", 0.0),       # Y坐标（米）
                "angle": pose_task.result.get("angle", 0.0), # 角度（弧度）
                "task_status": task_status,
                "ret_code": pose_task.result.get("ret_code", 0)
            }
            print(f"[SUCCESS] 位置查询完成 | 位置={robot_pose}")
            return robot_pose
        else:
            print(f"[FAILED] 位置查询执行失败 | 状态码={task_status} | 结果={pose_task.result}")
            return None
    else:
        print(f"[FAILED] 位置查询结果异常 | 结果={pose_task.result}")
        return None

# AGV 软急停控制流程（对应 6004/0x1774 接口）
def agv_soft_emc_process(robot: md.RobotManager, status: bool, wait_complete: bool = True):
    """
    AGV 软急停控制（触发/取消软急停）
    :param robot: 机器人管理器实例
    :param status: 软急停状态（True=触发输出急停，False=取消急停），必填不可缺省
    :param wait_complete: 是否等待配置任务执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：配置成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（严格匹配接口必填要求）
    if not isinstance(status, bool):
        print(f"[ERROR] status参数必须是布尔类型（True/False），当前输入：{status}（类型：{type(status)}）")
        return False

    # 2. 创建软急停任务（action=6004 对应接口编号）
    soft_emc_task = md.Task.create_task(
        action=6004,
        data={
            "status": status
        }
    )

    # 3. 下发任务（6004属于6000~7000区间，自动分配到other_worker）
    robot.add_task(soft_emc_task)
    emc_desc = "触发软急停" if status else "取消软急停"
    print(f"[Soft EMC] 已下发{emc_desc}指令 | 等待完成={wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # 等待模式：等待任务执行完成（复用现有wait_task_complete机制）
    wait_flag = robot.other_worker.wait_task_complete(soft_emc_task, timeout=5)

    # 4. 结果判断与日志输出
    if not wait_flag:
        print(f"[ERROR] 软急停指令执行超时：{emc_desc}")
        return False

    # 检查任务结果有效性
    if soft_emc_task.result is not None and isinstance(soft_emc_task.result, dict):
        task_status = soft_emc_task.result.get("task_status", -1)
        ret_code = soft_emc_task.result.get("ret_code", 0)
        if task_status == 4:
            print(f"[SUCCESS] 软急停指令执行完成：{emc_desc} | 错误码={ret_code}")
            return True
        else:
            print(f"[FAILED] 软急停指令执行失败：{emc_desc} | 状态码={task_status} | 错误码={ret_code} | 结果={soft_emc_task.result}")
            return False
    else:
        print(f"[FAILED] 软急停指令结果异常：{emc_desc} | 结果={soft_emc_task.result}")
        return False

# AGV 取消当前导航流程（对应 3003/0xBBB 接口）
def agv_nav_cancel_process(robot: md.RobotManager, wait_complete: bool = True):
    """
    AGV 取消当前正在执行的导航任务
    :param robot: 机器人管理器实例
    :param wait_complete: 是否等待取消任务执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：取消成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（无额外必填参数，仅做基础实例校验）
    if not isinstance(robot, md.RobotManager):
        print(f"[ERROR] robot参数必须为RobotManager实例，当前输入类型：{type(robot)}")
        return False

    # 2. 创建取消导航任务（action=3003 对应接口编号，JSON数据区为空）
    nav_cancel_task = md.Task.create_task(
        action=3003,
        data={}
    )

    # 3. 下发任务（3003属于3000~4000区间，自动分配到navigation_worker）
    robot.add_task(nav_cancel_task)
    print(f"[Nav Cancel] 已下发取消当前导航指令 | 等待完成={wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # 等待模式：等待任务执行完成（复用导航模块的wait_task_complete机制）
    wait_flag = robot.navigation_worker.wait_task_complete(nav_cancel_task, timeout=5)

    # 4. 结果判断与日志输出
    if not wait_flag:
        print(f"[ERROR] 取消导航指令执行超时")
        return False

    # 检查任务结果有效性，兼容接口返回字段
    if nav_cancel_task.result is not None and isinstance(nav_cancel_task.result, dict):
        task_status = nav_cancel_task.result.get("task_status", -1)
        ret_code = nav_cancel_task.result.get("ret_code", 0)
        err_msg = nav_cancel_task.result.get("err_msg", "无错误信息")
        if task_status == 4:
            print(f"[SUCCESS] 取消导航指令执行完成 | 错误码={ret_code}")
            return True
        else:
            print(f"[FAILED] 取消导航指令执行失败 | 状态码={task_status} | 错误码={ret_code} | 错误信息={err_msg} | 结果={nav_cancel_task.result}")
            return False
    else:
        print(f"[FAILED] 取消导航指令结果异常 | 结果={nav_cancel_task.result}")
        return False

# 设置安全激光动作流程（对应 4451/0x1163 接口）
def agv_set_safe_laser_process(robot: md.RobotManager, key: str, enable: bool, wait_complete: bool = True):
    """
    设置安全激光（启用/禁用指定激光）
    :param robot: 机器人管理器实例
    :param key: 激光的唯一标识（字符串，如"Laser-000"），必填
    :param enable: 是否启用该激光（True=启用，False=禁用），必填
    :param wait_complete: 是否等待配置任务执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：配置成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（避免无效参数）
    if not isinstance(key, str) or key.strip() == "":
        print(f"[ERROR] 激光key必须为非空字符串，当前输入：{key}")
        return False
    if not isinstance(enable, bool):
        print(f"[ERROR] enable参数必须是布尔类型（True/False），当前输入：{enable}（类型：{type(enable)}）")
        return False

    # 2. 创建安全激光配置任务（action=4451）
    laser_config_task = md.Task.create_task(
        action=4451,
        data={
            "key": key,
            "enable": enable
        }
    )

    # 3. 下发任务（4451属于4000~5000区间，自动分配到config_worker）
    robot.add_task(laser_config_task)
    print(f"[Set Safe Laser] 已下发配置：激光key={key}，启用状态={enable} | 等待完成={wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # 等待模式：等待任务执行完成（复用现有wait_task_complete机制）
    wait_flag = robot.config_worker.wait_task_complete(laser_config_task, timeout=5)

    # 4. 结果判断
    if not wait_flag:
        print(f"[ERROR] 安全激光配置超时：key={key}，enable={enable}")
        return False

    # 检查任务结果是否有效
    if laser_config_task.result is not None and isinstance(laser_config_task.result, dict):
        task_status = laser_config_task.result.get("task_status", -1)
        if task_status == 4:
            print(f"[SUCCESS] 安全激光配置完成：key={key}，enable={enable}")
            return True
        else:
            print(f"[FAILED] 安全激光配置失败：key={key}，enable={enable} | 状态码={task_status} | 结果={laser_config_task.result}")
            return False
    else:
        print(f"[FAILED] 安全激光配置结果异常：key={key}，enable={enable} | 结果={laser_config_task.result}")
        return False

# AGV 平移动作流程（对应 3055/0xBEF 接口，新增等待控制参数）
def agv_translate_process(robot: md.RobotManager, dist: float, vx: float = 0.0, vy: float = 0.0, mode: int = 0, wait_complete: bool = True):
    """
    AGV 直线平移动作（绝对距离，新增等待控制参数）
    :param robot: 机器人管理器实例
    :param dist: 平移距离（绝对值，单位：米），必须>0
    :param vx: 机器人坐标系X方向速度（正向前/负向后，单位：m/s）
    :param vy: 机器人坐标系Y方向速度（正向左/负向右，单位：m/s）
    :param mode: 运动模式 0=里程模式（默认）/1=定位模式
    :param wait_complete: 是否等待平移动作执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（避免无效参数）
    if dist <= 0:
        print(f"[ERROR] 平移距离必须大于0，当前值：{dist}")
        return False
    if vx == 0 and vy == 0:
        print(f"[ERROR] X/Y方向速度不能同时为0，请设置有效速度")
        return False

    # 2. 创建平移任务（3055 对应平移动作）
    translate_task = md.Task.create_task(
        action=3055,
        data={
            "dist": abs(dist),  # 强制转为绝对值（接口要求）
            "vx": vx,
            "vy": vy,
            "mode": mode
        }
    )

    # 3. 下发平移任务（3055 属于导航类任务，自动分配到 navigation_worker）
    robot.add_task(translate_task)

    # 非等待模式：仅下发任务，直接返回True（任务已下发）
    if not wait_complete:
        print(f"[AGV Translate] 已下发平移任务：距离={dist}m | Vx={vx}m/s | Vy={vy}m/s | 模式={mode} | 不等待执行完成")
        return True

    # 等待模式：轮询查询任务状态（复用 1020 接口查询任务状态）
    status_task = md.Task.create_task(1020, {"simple": True})
    print(f"[AGV Translate] 开始平移：距离={dist}m | Vx={vx}m/s | Vy={vy}m/s | 模式={mode}")

    while True:
        time.sleep(0.1)  # 缩短轮询周期（平移动作响应更快）
        
        # 添加状态查询任务
        robot.state_worker.add_task(status_task)
        # 等待任务响应（超时5秒）
        flag = robot.state_worker.wait_task_complete(status_task, timeout=5)

        # 异常处理：任务结果为空/格式错误
        if status_task is None or not hasattr(status_task, 'result') or status_task.result is None:
            print("[ERROR] 平移状态查询失败：任务对象为空或通信超时")
            return False
        if not isinstance(status_task.result, dict):
            continue

        # 任务完成判断（task_status != 2 表示任务未执行/已完成）
        if flag and status_task.result.get("task_status") != 2:
            break

    # 5. 判断平移结果（task_status=4 表示执行成功）
    final_status = status_task.result.get("task_status", -1)
    if final_status == 4:
        print(f"[SUCCESS] AGV 平移完成 | 最终状态码：{final_status}")
        return True
    else:
        print(f"[FAILED] AGV 平移失败 | 最终状态码：{final_status} | 详情：{status_task.result}")
        return False

# AGV 转动动作流程（对应 3056/0xBF0 接口）
def agv_turn_process(robot: md.RobotManager, angle: float, vw: float, mode: int = 0, wait_complete: bool = True):
    """
    AGV 原地转动动作（固定角速度旋转固定角度，新增等待控制参数）
    :param robot: 机器人管理器实例
    :param angle: 转动角度（绝对值，单位：弧度 rad），必须>0
    :param vw: 转动角速度（正为逆时针，负为顺时针，单位：rad/s），不能为0
    :param mode: 运动模式 0=里程模式（默认）/1=定位模式
    :param wait_complete: 是否等待转动动作执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 1. 参数校验（避免无效参数）
    if angle <= 0:
        print(f"[ERROR] 转动角度必须大于0，当前值：{angle} rad")
        return False
    if vw == 0:
        print(f"[ERROR] 角速度vw不能为0，请设置有效角速度")
        return False

    # 2. 创建转动任务（3056 对应转动动作）
    turn_task = md.Task.create_task(
        action=3056,
        data={
            "angle": abs(angle),  # 强制转为绝对值（接口要求）
            "vw": vw,
            "mode": mode
        }
    )

    # 3. 下发转动任务（3056 属于导航类任务，自动分配到 navigation_worker）
    robot.add_task(turn_task)
    direction = "逆时针" if vw > 0 else "顺时针"

    # 非等待模式：仅下发任务，直接返回True（任务已下发）
    if not wait_complete:
        print(f"[AGV Turn] 已下发转动任务：角度={angle}rad | 角速度={vw}rad/s ({direction}) | 模式={mode} | 不等待执行完成")
        return True

    # 等待模式：保留原有轮询查询逻辑（以下为原代码，仅优化日志）
    # 4. 轮询查询任务状态（复用 1020 接口查询任务状态）
    status_task = md.Task.create_task(1020, {"simple": True})
    print(f"[AGV Turn] 开始转动：角度={angle}rad | 角速度={vw}rad/s ({direction}) | 模式={mode}")

    while True:
        time.sleep(0.1)  # 轮询周期
        
        # 添加状态查询任务
        robot.state_worker.add_task(status_task)
        # 等待任务响应（超时5秒）
        flag = robot.state_worker.wait_task_complete(status_task, timeout=5)

        # 异常处理：任务结果为空/格式错误
        if status_task is None or not hasattr(status_task, 'result') or status_task.result is None:
            print("[ERROR] 转动状态查询失败：任务对象为空或通信超时")
            return False
        if not isinstance(status_task.result, dict):
            continue

        # 任务完成判断（task_status != 2 表示任务未执行/已完成）
        if flag and status_task.result.get("task_status") != 2:
            break

    # 5. 判断转动结果（task_status=4 表示执行成功）
    final_status = status_task.result.get("task_status", -1)
    if final_status == 4:
        print(f"[SUCCESS] AGV 转动完成 | 最终状态码：{final_status}")
        return True
    else:
        print(f"[FAILED] AGV 转动失败 | 最终状态码：{final_status} | 详情：{status_task.result}")
        return False    
# 获取机器人位置流程（试例）
def get_robot_pose(robot: md.RobotManager):
    task = md.Task.create_task(1020,{"simple":True})    # 1004为API的任务类型编号
    robot.add_task(task)        #添加任务
    robot.state_worker.wait_task_complete(task, timeout=5)   #等待任务完成，抛出timeout异常
    print(f"[Robot Pose] Result: {task.result}")
    
    #task_status = task.result.get('task_status') 
    #print(f"[Robot Pose] task_status: {task_status}")
    
    return task.result

# 设置机器人配置流程（试例）
def set_robot_config(robot: md.RobotManager):
    task = md.Task.create_task(4100, {
        "NetProtocol": {
            "RobotName": "RD-TEST-1", # 机器人名称
            "RobotNote": "test car1" # 机器人备注
        },
        "MoveFactory": {
            "3DCameraHole": True # 导航是否使用3D相机检测坑洞
        }
    })
    robot.add_task(task)
    robot.state_worker.wait_task_complete(task, timeout=5)
    return task.result


# 路径定位流程
def locate_process(robot: md.RobotManager):
    # 重定位执行段
    robot.add_task(md.Task.create_task(2002, {"x":1.0,"y":2.0,"angle":-3.12}))
    # 查询重定位段
    task1 = md.Task.create_task(1021, {})
    while True:
        time.sleep(1)  #轮询周期
        robot.state_worker.add_task(task1)      #添加任务
        flag = robot.state_worker.wait_task_complete(task1, timeout=5)        #等待任务完成，抛出timeout异常
        if flag and task1.result["reloc_status"] == 1:       #检查结果
            print(f"locate success")
            break

        
        
# 路径导航流程
def navigation_process(robot: md.RobotManager, target_id, wait_complete: bool = True):
    """
    机器人导航流程（新增等待控制参数）
    :param robot: 机器人管理器实例
    :param target_id: 导航目标点ID（如"LM2"）
    :param wait_complete: 是否等待导航动作执行完成（True=等待完成，False=仅下发任务不等待）
    :return: bool - 等待模式下：成功返回True，失败返回False；非等待模式下：任务下发成功返回True
    """
    # 执行导航移动段（仅下发任务，核心逻辑保留）
    nav_task = md.Task.create_task(3051, {"source_id": "SELF_POSITION","id": target_id})
    robot.add_task(nav_task)
    print(f"[导航任务] 已下发到目标点 {target_id} | 等待执行完成：{wait_complete}")

    # 非等待模式：仅下发任务，直接返回True（任务已下发）
    if not wait_complete:
        return True

    # 等待模式：保留原有状态查询逻辑（以下为原代码，仅优化注释和日志）
    task2 = md.Task.create_task(1020, {"simple": True})
    while True:
        time.sleep(0.1)
        robot.state_worker.add_task(task2)
        flag = robot.state_worker.wait_task_complete(task2, timeout=5)
        
        # 异常处理：任务对象/结果异常
        if task2 is None or not hasattr(task2, 'result') or task2.result is None:
            print("[ERROR] 任务对象为空或通信超时，请检查机器人连接状态")
            return False

        # 结果格式异常：继续轮询
        if not isinstance(task2.result, dict):
            print("[导航状态] 结果格式非字典，继续查询...")
            continue
        if isinstance(task2.result, str):
            print("[导航状态] 结果为字符串，继续查询...")
            continue

        # 任务完成判断（task_status != 2 表示执行完成/终止）
        if flag and task2.result["task_status"] != 2:
            break

    # 等待模式：返回导航执行结果
    if task2.result["task_status"] == 4:
        print(f"[导航完成] 成功到达目标点 {target_id}")
        return True
    else:
        print(f"[导航失败] 目标点 {target_id} | 状态码：{task2.result['task_status']}")
        return False

def advanced_navigation_process(
    robot: md.RobotManager,
    target_id: str,
    source_id: str = "SELF_POSITION",
    angle: float = None,
    method: str = 'forward',
    max_speed: float = None,
    max_wspeed: float = None,
    max_acc: float = None,
    max_wacc: float = None,
    duration: int = None,
    orientation: int = None,
    spin: bool = None,
    delay: int = None,
    start_rot_dir: int = None,
    end_rot_dir: int = None,
    reach_dist: float = None,
    reach_angle: float = None,
    skill_name: str = None,
    task_id: str = None,
    wait_complete: bool = True
):
    """
    高级路径导航（支持全自定义可选参数）
    :param robot: 机器人管理器实例
    :param target_id: 目标站点名称（必填，如"LM1"）
    :param source_id: 起始站点名称，默认"SELF_POSITION"（当前位置）
    :param angle: 目标站点角度（世界坐标系，单位rad）
    :param method: 运动方式，仅支持"forward"/"backward"
    :param max_speed: 最大线速度（m/s）
    :param max_wspeed: 最大角速度（rad/s）
    :param max_acc: 最大线加速度（m/s²）
    :param max_wacc: 最大角加速度（rad/s²）
    :param duration: 导航结束后等待时间（ms）
    :param orientation: 全向车保持角度（暂不使用）
    :param spin: 是否随动（bool）
    :param delay: 延迟结束导航状态时间（ms，默认0）
    :param start_rot_dir: 起步原地旋转方向（-1=顺时针, 0=就近, 1=逆时针）
    :param end_rot_dir: 到点原地旋转方向（-1=顺时针, 0=就近, 1=逆时针）
    :param reach_dist: 到点位置精度（m）
    :param reach_angle: 到点角度精度（rad）
    :param skill_name: 动作类型（"Action"/"GotoSpecifiedPose"）
    :param task_id: 任务编号
    :param wait_complete: 是否等待导航完成（True=等待，False=仅下发）
    :return: bool - 等待模式下成功返回True，失败返回False；非等待模式下任务下发成功返回True
    """
    # -------------------------- 1. 参数合法性校验 --------------------------
    if not target_id or not isinstance(target_id, str):
        print(f"[ERROR] target_id 必须为非空字符串，当前值：{target_id}")
        return False
    if method is not None and method not in ["forward", "backward"]:
        print(f"[ERROR] method 只能是 'forward' 或 'backward'，当前值：{method}")
        return False
    if start_rot_dir is not None and start_rot_dir not in [-1, 0, 1]:
        print(f"[ERROR] start_rot_dir 只能是 -1/0/1，当前值：{start_rot_dir}")
        return False
    if end_rot_dir is not None and end_rot_dir not in [-1, 0, 1]:
        print(f"[ERROR] end_rot_dir 只能是 -1/0/1，当前值：{end_rot_dir}")
        return False
    # 数值类参数非负校验
    for param, name in [
        (max_speed, "max_speed"), (max_wspeed, "max_wspeed"),
        (max_acc, "max_acc"), (max_wacc, "max_wacc"),
        (duration, "duration"), (delay, "delay"),
        (reach_dist, "reach_dist"), (reach_angle, "reach_angle")
    ]:
        if param is not None and param < 0:
            print(f"[ERROR] {name} 不能为负数，当前值：{param}")
            return False

    # -------------------------- 2. 构造导航任务数据 --------------------------
    nav_data = {
        "source_id": source_id,
        "id": target_id
    }
    # 仅添加非None的可选参数（符合接口"可缺省"要求）
    if angle is not None: nav_data["angle"] = angle
    if method is not None: nav_data["method"] = method
    if max_speed is not None: nav_data["max_speed"] = max_speed
    if max_wspeed is not None: nav_data["max_wspeed"] = max_wspeed
    if max_acc is not None: nav_data["max_acc"] = max_acc
    if max_wacc is not None: nav_data["max_wacc"] = max_wacc
    if duration is not None: nav_data["duration"] = duration
    if orientation is not None: nav_data["orientation"] = orientation
    if spin is not None: nav_data["spin"] = spin
    if delay is not None: nav_data["delay"] = delay
    if start_rot_dir is not None: nav_data["start_rot_dir"] = start_rot_dir
    if end_rot_dir is not None: nav_data["end_rot_dir"] = end_rot_dir
    if reach_dist is not None: nav_data["reach_dist"] = reach_dist
    if reach_angle is not None: nav_data["reach_angle"] = reach_angle
    if skill_name is not None: nav_data["skill_name"] = skill_name
    if task_id is not None: nav_data["task_id"] = task_id

    # -------------------------- 3. 下发导航任务 --------------------------
    nav_task = md.Task.create_task(3051, nav_data)
    robot.add_task(nav_task)
    print(f"[高级导航] 已下发任务：{source_id} → {target_id} | 配置：{nav_data} | 等待完成：{wait_complete}")

    # 非等待模式：仅下发任务，直接返回成功
    if not wait_complete:
        return True

    # -------------------------- 4. 等待模式：轮询查询状态 --------------------------
    status_task = md.Task.create_task(1020, {"simple": True})
    while True:
        time.sleep(0.1)
        robot.state_worker.add_task(status_task)
        flag = robot.state_worker.wait_task_complete(status_task, timeout=5)

        # 异常处理：任务结果为空/格式错误
        if status_task is None or not hasattr(status_task, 'result') or status_task.result is None:
            print("[ERROR] 导航状态查询失败：任务对象为空或通信超时")
            return False
        if not isinstance(status_task.result, dict):
            continue

        # 任务完成判断（task_status != 2 表示执行完成/终止）
        if flag and status_task.result.get("task_status") != 2:
            break

    # -------------------------- 5. 判断导航结果 --------------------------
    final_status = status_task.result.get("task_status", -1)
    if final_status == 4:
        print(f"[SUCCESS] 高级导航完成：{source_id} → {target_id}")
        return True
    else:
        print(f"[FAILED] 高级导航失败：{source_id} → {target_id} | 状态码：{final_status} | 结果：{status_task.result}")
        return False

if __name__ == '__main__':
    robot = md.RobotManager.create_with_workers()    # 创建机器人对象
    robot.connect('192.168.1.52')    # 连接机器人
    robot.navigation_worker
    #locate_process(robot)
    
    
    while True:
        navigation_process(robot,"LM2") 
        time.sleep(1)
        navigation_process(robot,"LM3")  
        time.sleep(1)
        navigation_process(robot,"LM1")   
        time.sleep(1) 
    robot.close()      # 关闭socket连接
 