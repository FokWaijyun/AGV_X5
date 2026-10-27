"""
Group: utils.py模块
Description: 实现了socket网络包的打包和解包工具
Date: 2025-03-20 (add at v1.0.0)
"""
import socket
import json
import logging
import struct
import asyncio

PACK_FMT_STR = '!BBHLH6s'

logger = logging.getLogger("robot-client")

# 生成器
def cyclic_num_generator(start=100, end=65535):
    while True:
        for num in range(start, end + 1):
            yield num

# 使用这个生成器
cyclic_num_id = cyclic_num_generator()
def get_num_id():
    '''
    获取一个自增的数字ID
    '''
    return next(cyclic_num_id)


def packMasg(reqId: int, msgType: int, msg={})-> bytes:
    '''
    转二进制网络包, 报文头部的长度为 1 + 1 + 2 + 4 + 2 + 6 = 16字节
    Args:
        reqId: 请求ID（自定义 0 ~ 65535）
        msgType: 消息类型
        msg: 消息内容
    '''
    msgLen = 0
    jsonStr = json.dumps(msg)   # 将Python对象编码成JSON字符串
    if (msg != {}):
        msgLen = len(jsonStr)
    rawMsg = struct.pack(PACK_FMT_STR, 0x5A, 0x01, reqId, msgLen, msgType, b'\x00\x00\x00\x00\x00\x00')
    # print("{:02X} {:02X} {:04X} {:08X} {:04X}".format(0x5A, 0x01, reqId, msgLen, msgType))
    if (msg != {}):
        try:
            rawMsg += bytearray(jsonStr,'ascii')    # ASCII编码
            logger.info(f"packMasg: {msg}")
        except UnicodeEncodeError as e:
            logger.error("packMasg: jsonStr error")
        
    return rawMsg


def recvMsg(so: socket.socket):
    '''
    接收一条消息(阻塞)（socket未关闭）
    Returns:
        - 消息内容(dict)
        - 消息头(List[5])
    '''
    databytes = b''
    try:
        data = so.recv(16)
    except socket.timeout:
        logger.warning('recvMsg: header timeout')
        raise socket.timeout
    jsonDataLen = 0     # 消息体长度
    backReqNum = 0      # 返回的请求种类编号
    if(len(data) < 16):
        logger.error('recvMsg: pack head error')
        raise socket.error
    else:
        header = struct.unpack(PACK_FMT_STR, data)
        # print("{:02X} {:02X} {:04X} {:08X} {:04X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X}       length: {}"
        # .format(header[0], header[1], header[2], header[3], header[4],
        # header[5][0], header[5][1], header[5][2], header[5][3], header[5][4], header[5][5],
        # header[3]))
        jsonDataLen = header[3]
        backReqNum = header[4]
    databytes += data
    # 处理消息体
    data = b''
    readSize = 1024
    try:
        if jsonDataLen < readSize:
            readSize = jsonDataLen
        while (jsonDataLen > 0):
            recv = so.recv(readSize)
            if not recv:
                break  # 如果 recv 返回空数据，说明连接被关闭
            data += recv    # TODO: data.extend(recv)  # 使用 extend 方法追加数据
            jsonDataLen -= len(recv)
            if jsonDataLen < readSize:
                readSize = jsonDataLen
        logger.debug(json.dumps(json.loads(data), indent=1))
        # print(' '.join('{:02X}'.format(x) for x in dataall))
        databytes += data
        datadict = json.loads(data)
    except socket.timeout:
        logger.error('recvMsg: timeout')
        raise socket.timeout

    return (datadict, header)


# (停用)
async def asyncRecvMsg(reader: asyncio.StreamReader):
    '''
    接收一条消息
    Returns:
        - 消息内容(dict)
        - 消息头(List[5])
    '''
    # 处理消息头

    data = reader.read(16)

    jsonDataLen = 0     # 消息体长度
    backReqNum = 0      # 返回的请求种类编号
    if(len(data) < 16):
        logger.error('recvMsg: pack head error')
        raise socket.error
    else:
        header = struct.unpack(PACK_FMT_STR, data)  # 解码消息头为数组
        # (header[0], header[1], header[2], header[3], header[4], header[5][0], header[5][1], header[5][2], header[5][3], header[5][4], header[5][5])
        jsonDataLen = header[3]
        backReqNum = header[4]

    # 处理消息体
    data = b''
    readSize = 1024
    if jsonDataLen < readSize:
        readSize = jsonDataLen
    while (jsonDataLen > 0):
        recv = reader.read(readSize)
        if not recv:
            break  # 如果 recv 返回空数据，说明连接被关闭
        data += recv    # TODO: data.extend(recv)  # 使用 extend 方法追加数据
        jsonDataLen -= len(recv)
        if jsonDataLen < readSize:
            readSize = jsonDataLen
    logger.debug(json.dumps(json.loads(data), indent=1))

    datadict = json.loads(data)

    return (datadict, header)


