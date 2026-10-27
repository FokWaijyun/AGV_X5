"""
Group: models.py模块
Description:
两种调用方式：
- 生产者-消费者模式：利用回调，核心是将任务的创建（生产者）和任务的执行（消费者）解耦（新线程），通过一个共享的任务队列来协调两者。
- 异步模式：利用Future/Promise。通过Future/Promise来获取任务执行结果。
Date: 2025-03-20 (add at v1.0.0)
"""
import logging
import uuid
import json
import asyncio
import socket
import queue
import threading
import time
from datetime import datetime
from enum import Enum
from utils import recvMsg, packMasg, asyncRecvMsg, get_num_id

logger = logging.getLogger("robot-client")

# 断开最大重试次数
MAX_RETRIES = 5
# 断开重试间隔时间（秒）
RETRY_INTERVAL = 2

def create_socket():
    """创建并返回一个新的 socket 对象"""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #设置TCP Keepalive
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)      #设置Keepalive允许的空闲时长为60秒
    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 8)        #设置Keepalive探测次数为8次
    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)     #设置Keepalive探测间隔为10秒
    return client_socket


# SECTION - Task


class TaskStatus(Enum):
    pending = 'pending'
    processing = 'processing'
    success = 'success'
    failed = 'failed'


class Task:
    '''任务类
        {
            "task_id": str/int,       # 唯一任务标识(1~65535)
            "action": int,            # 操作类型编号
            "status": str,            # 任务状态（pending/processing/success/failed）
            "result": dict,           # 执行结果或错误信息
            "created_at": datetime,   # 任务创建时间
            "complete_at": datetime,   # 任务完成时间
        }
    '''
    
    def __init__(self, task_id: str, action, data: dict, callback, status: TaskStatus, result: dict, created_at: datetime, complete_at: datetime = None):
        # 初始值
        self.task_id = task_id  #  初始化任务ID
        self.action = action    # 操作类型
        self.data = data        # 传送数据
        self.callback = callback # 回调函数
        # 返回值
        self.status = status    # 任务状态（pending/running/success/failed）
        self.result = result    # 执行结果或错误信息
        self.created_at = created_at  # 任务创建时间
        self.complete_at = complete_at  # 任务完成时间
        # 其他
        self.done_event = threading.Event()


    
    @staticmethod
    def create_task(action, data={}, callback=None, status=TaskStatus.pending):
        '''创建一个任务实例'''
        # 生成一个随机的task_id
        task_id = get_num_id()
        # 创建一个任务
        task = Task(task_id, action, data, callback, status, None, datetime.now())
        return task
    
    def do_task_with_socket(self, so : socket.socket):
        '''执行任务'''
        self.status = TaskStatus.processing
        logger.info(f"Processing task: {self.task_id}")
        so.send(packMasg(self.task_id, self.action, self.data))
        res, header = recvMsg(so)  # 阻塞式接收消息

        self.result = res
        self.status = TaskStatus.success
        self.complete_at = datetime.now()
        logger.info(f"Completed task {self.task_id} successfully")
    
    # （废弃）
    def send_msg(self)-> list:
        '''
        发送消息并得到结果，阻塞式
        '''
        self.status = 'processing'
        self.so.connect((self.ip, self.port))
        self.so.settimeout(5)

        action_msgs = [packMasg(index, action.cmd, action.data) for index, action in enumerate(self.action)] # "task_ids":["SEER78914"]11004
        action_res = []
        for action_msg in action_msgs:
            print("\n\nreq:")
            print(' '.join('{:02X}'.format(x) for x in action_msg))
            self.so.send(action_msg)
            res = recvMsg(self.so)
            action_res.append(res)

        self.so.close()
        self.status = 'success'
        return action_res
    
# （废弃）
class CustomTask(Task):
    '''自定义任务类'''
    def __init__(self, task_id: str, action, data: dict, do_task, callback, status: TaskStatus, result: dict, created_at: datetime, complete_at: datetime = None):
        super().__init__(task_id, action, data, callback, status, result, created_at, complete_at)
        self.do_task = self.do_task

    @staticmethod
    def create_task(action, data={}, do_task=None, callback=None, status=TaskStatus.pending):
        '''创建一个任务实例'''
        # 生成一个随机的task_id
        task_id = get_num_id()
        # 创建一个任务
        task = Task(task_id, action, data, do_task, callback, status, None, datetime.now())
        return task
    
    def do_task_with_socket(self, so : socket.socket):
        '''执行任务'''
        self.status = TaskStatus.processing
        logger.info(f"Processing task: {self.task_id}")

        self.do_task(self, so)

        self.status = TaskStatus.success
        self.complete_at = datetime.now()
        logger.info(f"Completed task {self.task_id} successfully")


# SECTION - TaskWorker


class TaskWorker:
    '''任务执行器, 维护了任务队列，接收结果'''

    def __init__(self):
        # 状态相关(未用)
        self.state_queue = queue.Queue()
        # 任务相关
        self.task_queue = queue.Queue()  # 任务队列
        self.thread = None
        # 连接相关
        self.so = create_socket()

        self.ip = None
        self.port = None

    #------------------- 内部调用 --------------------#
    # 任务循环，从队列中获取任务并执行（one by one）
    def _start_task_loop(self):
        while True:
            pre_task = self.task_queue.get()  # 阻塞式从队列中获取任务
            # 如果收到 None，退出循环
            if pre_task is None:
                # 资源释放
                self.task_queue.task_done()
                self.so.close()
                break

            # 处理任务
            try:
                pre_task.do_task_with_socket(self.so)
            except (socket.timeout, ConnectionError):
                # 超时断开，socket重试机制
                res = self._auto_reconnect()
                if res:
                    logger.warning(f"Reconnected to server, retrying task {pre_task.task_id}...")
                    self.so.send(packMasg(pre_task.task_id, pre_task.action.cmd, pre_task.action.data))
                    res, header = recvMsg(self.so)  # 阻塞式接收消息

                    pre_task.result = res
                    pre_task.status = TaskStatus.success
                    pre_task.complete_at = datetime.now()
                    logger.info(f"Completed task {pre_task.task_id} successfully")
                else:
                    logger.warning(f"Task {pre_task.task_id} timed out, retrying...")
                    pre_task.status = TaskStatus.failed
                    pre_task.result = "Task timed out"
                    pre_task.complete_at = datetime.now()

            except Exception as e:
                pre_task.result = e
                pre_task.status = TaskStatus.failed
                pre_task.complete_at = datetime.now()
                logger.warning(f"Error processing task {pre_task.task_id}: {e}")
            finally:
                # 标记任务完成
                pre_task.done_event.set()
                self.task_queue.task_done()
                self._complete_callback(pre_task)

    @staticmethod
    def _complete_callback(task):
        """任务完成后的回调函数"""
        if task.callback is not None:
            task.callback(task)
        return

    def _auto_reconnect(self):
        '''
        断开自动重连（阻塞式）
        '''
        def connect_to_server(client_socket, host, port):
            """尝试连接到服务器"""
            try:
                client_socket.connect((self.ip, self.port))
                client_socket.settimeout(5)
                return True
            except Exception as e:
                return False

        retries = 0
        while retries < MAX_RETRIES:

            if connect_to_server(self.so, self.ip, self.port):
                break
            else:
                retries += 1
                print(f"正在尝试第 {retries} 次重连...")
                time.sleep(RETRY_INTERVAL)
        else:
            print("重试次数已达上限，无法连接到服务器。")
            return False
        return True

    
    #------------------- 外部调用 --------------------#

    def connect(self, ip, port):
        """连接机器人，并启动任务循环（消费者）"""
        self.ip = ip
        self.port = port
        self.so.connect((self.ip, self.port))
        self.so.settimeout(5)
        self.thread = threading.Thread(target=self._start_task_loop, daemon=True)
        self.thread.start()

    def close(self):
        """关闭连接（到所有任务完成后）"""
        try:
            # 停止线程
            self.task_queue.put(None)
        except Exception as e:
            logger.error(f"Error during close: {e}")

    def wait_and_close(self, timeout=None):
        """关闭连接，会阻塞等待队列中任务完成"""
        try:
            # 停止线程
            self.task_queue.put(None)
            # 阻塞直到所有任务完成
            # self.task_queue.join()
            self.thread.join(timeout=timeout)
        except Exception as e:
            logger.error(f"Error during close: {e}")
        finally:
            # 清理资源
            if self.thread.is_alive():
                self.thread.join(timeout=1)  # 再次尝试等待
            if not self.task_queue.empty():
                # 清空队列
                self.task_queue.queue.clear()

    def add_task(self, task):
        """添加任务到任务队列（生产者）"""
        self.task_queue.put(task)

    def wait_task_complete(self, task, timeout=None) -> bool:
        """等待任务完成（对外的阻塞方法）"""
        flag = task.done_event.wait(timeout=timeout)
        if timeout and not flag:
            return False
        return True

    def wait_all_task_complete(self):
        """等待所有任务完成（对外的阻塞方法）"""
        self.task_queue.join()


class AsyncTaskWorker:
    '''异步任务执行器，（单线程模式）'''

    def __init__(self):

        # 连接相关
        self.reader = None
        self.writer = None
    #-------------------- 异步模式 --------------------#
    async def connect(self, ip, port):
        """异步连接机器人，并启动任务循环"""
        self.reader, self.writer = await asyncio.open_connection(ip, port)

    async def close(self):
        """异步关闭连接（到所有任务完成后）"""
        self.writer.close()
        await self.writer.wait_closed()

    async def add_task(self, task):
        """异步添加任务到任务队列"""
        # 处理任务
        try:
            task.status = TaskStatus.processing
            logger.info(f"Processing task: {task.task_id}")
            # 耗时操作(task)
            self.writer.write(packMasg(task.task_id, task.action.cmd, task.action.data))
            await self.writer.drain()  # 等待数据发送完成

            # 接收响应
            res, header = await asyncRecvMsg(self.reader)  # 异步式接收消息

            task.result = res
            task.status = TaskStatus.success
            task.complete_at = datetime.now()
            logger.info(f"Completed task {task.task_id} successfully")
        except Exception as e:
            task.result = e
            task.status = TaskStatus.failed
            task.complete_at = datetime.now()
            logger.warning(f"Error processing task {task.task_id}: {e}")
        return task


# SECTION - 用户访问


class RobotMapper:
    """机器人功能模块映射器（ORM类）（代理类）TODO
    - 状态、信息存储
    - 任务下发
    - 任务结果获取
    - （用户可访问的类）
    
    """

    def __init__(self, worker: TaskWorker):
        self.ip = None
        self.port = None
        self.tasks = {}  # 存储任务内容的字典(未用)
        self.worker = worker
        pass

    def connect(self, ip, port):
        self.worker.connect(ip, port)
        pass

    def get_data(self, task_id):
        return self.tasks[task_id]
    
    def set_data(self, task):
        self.tasks[task.task_id] = task
        self.worker.add_task(task)
        return

    def close(self):
        self.worker.close()
        return


class RobotState(RobotMapper):
    """机器人状态 TODO """
    def __init__(self, worker: TaskWorker):  # ← 添加 worker 参数
        super().__init__(worker)              # ← 传给父类
        return


class RobotAction(RobotMapper):
    """机器人动作 TODO """
    def __init__(self, worker: TaskWorker):  # ← 添加 worker 参数
        super().__init__(worker)              # ← 传给父类
        return


class RobotManager:
    """机器人模块管理器，用户主要访问入口（整合类）
    """

    def __init__(self, state_worker, control_worker, navigation_worker, config_worker, other_worker):

        # 任务执行相关
        self.state_worker = state_worker
        self.control_worker = control_worker
        self.navigation_worker = navigation_worker
        self.config_worker = config_worker
        self.other_worker = other_worker
        # 功能类 插件
        self.robot_state :RobotState = RobotState(self.state_worker)
        self.robot_control :RobotAction = RobotAction(self.control_worker)
        self.robot_navigation :RobotAction = RobotAction(self.navigation_worker)
        return

    @classmethod
    def create_with_workers(cls, worker_count=5):
        workers = [TaskWorker() for _ in range(worker_count)]
        return cls(*workers)

    def connect(self, ip):

        self.state_worker.connect(ip, 19204)
        self.control_worker.connect(ip, 19205)
        self.navigation_worker.connect(ip, 19206)
        self.config_worker.connect(ip, 19207)
        self.other_worker.connect(ip, 19210)
        return


    def close(self):
        self.state_worker.close()
        self.control_worker.close()
        self.navigation_worker.close()
        self.config_worker.close()
        self.other_worker.close()
        return


    def add_task(self, task: Task):
        """根据任务类型，选择对应的任务执行器"""
        if task.action >= 1000 and task.action < 2000:
            self.state_worker.add_task(task)
            return self.state_worker
        elif task.action >= 2000 and task.action < 3000:
            self.control_worker.add_task(task)
            return self.control_worker
        elif task.action >= 3000 and task.action < 4000:
            self.navigation_worker.add_task(task)
            return self.navigation_worker
        elif task.action >= 4000 and task.action < 5000:
            self.config_worker.add_task(task)
            return self.config_worker
        elif  task.action >= 6000 and task.action < 7000:
            self.other_worker.add_task(task)
            return self.other_worker
        else:
            logger.error(f"Unknown action type: {task.action}")
            raise Exception(f"Unknown action type: {task.action}")
        return 

    def wait_all_task_complete(self):
        self.state_worker.wait_all_task_complete()
        self.control_worker.wait_all_task_complete()
        self.navigation_worker.wait_all_task_complete()
        self.config_worker.wait_all_task_complete()
        self.other_worker.wait_all_task_complete()
        return
    
