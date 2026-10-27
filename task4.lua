local Normal_VISION_NO = 0
local Offset_VISION_NO = 1

local Normal_TOOL_index = 0
local Offset_TOOL_index = 1

local DO_NO = {
    inhale = 2, -- 吸气
    exhale = 3, -- 吹气    
}

local PalletPOS = {
    Start = GetPENV(0),
    Row = GetPENV(1),
    Col = GetPENV(2),
    prep_pal = GetPENV(3), -- 码垛放料准备点位
}

local PickPOS = {
    Start = GetPENV(4), -- 程序开始点位
    prep_pick = GetPENV(5), -- 抓取准备点位
}

-- 纠偏点位。
local OffsetPOS = {
    cam = GetPENV(6), -- 纠偏拍照点位
    prep_offset = GetPENV(7), -- 纠偏准备点位
}

-- 取料和放料，接近和离开偏移量（50 mm）。
local UOF = NewPose(0, 0, 50, 0, 0, 0)

local PlrList = {}


local function Init()
    -- 初始化代码
    MovJ(GetCPoint(), {uof = UOF})
    MovJ(PickPOS.Start)

    for i = 0, 6 do
        SetDO(i, 0)
    end
    Pallet.Load(1, PalletPOS.Start, PalletPOS.Row, PalletPOS.Col, 5, 4, 1, 1)

    for i = 1, 5 do
        for j = 1, 4 do
            PlrList[(i-1) * 4 + j] = Pallet.GetPose(1, {i, j, 1})
        end
    end

    VisionRun(Normal_VISION_NO)
    VisionRun(Offset_VISION_NO)
end


local function SpreadMaterials()
    SetDO({6, 5, 4}, 6) -- 110
    Delay(1)
    SetDO({6, 5, 4}, 7) -- 111
    Delay(1)
    SetDO({6, 5, 4}, 5) -- 101
    Delay(1)
    SetDO({6, 5, 4}, 0) -- 000
    Delay(4)
end


local function Do1pick()
    -- 抓取一个物料，不触发拍照，回到抓取准备点位。
    -- MovJ(PickPOS.prep_pick)
    VisionGetData(Normal_VISION_NO) -- 拍照不在pick函数中触发

    local PickPoint = CopyPoint(PickPOS.prep_pick)
    local VisionPose = GetVR(Normal_VISION_NO, 2)
    
    PickPoint.uf = Normal_VISION_NO
    PickPoint.tf = Normal_TOOL_index
    PickPoint.x = VisionPose.x
    PickPoint.y = VisionPose.y
    PickPoint.z = -104
    PickPoint.c = VisionPose.c
    
    MovJ(PickPoint, {uof = UOF})
    MovJ(PickPoint)

    SetDO(DO_NO.inhale, 1)
    Delay(0.2)
    MovJ(PickPoint, {uof = UOF})
    MovJ(PickPOS.prep_pick)

    VisionClearData(Normal_VISION_NO, 1) -- 清除视觉工艺 0 的缓存区第一个数据。
end


local function Voffset()
    -- 纠偏拍照动作
    MovJ(OffsetPOS.prep_offset)
    MovJ(OffsetPOS.cam)

    VisionTrig(Offset_VISION_NO, { timeout = 2 })
    VisionGetData(Offset_VISION_NO)
    VisionSetTF(Offset_VISION_NO, Offset_TOOL_index, OffsetPOS.cam)

    VisionClearData(Offset_VISION_NO, 1)

    MovJ(OffsetPOS.prep_offset)
end


local function Do1place(PlacePoint)
    -- 放置一个物料，回到抓取准备点位。
    SetTFNo(Offset_TOOL_index) -- 使用纠偏工具坐标系进行码垛

    MovJ(PalletPOS.prep_pal)
    MovJ(PlacePoint, {uof = UOF})
    MovJ(PlacePoint)
    SetDO(DO_NO.exhale, 1)
    Delay(0.2)
    SetDO(DO_NO.exhale, 0)
    MovJ(PlacePoint, {uof = UOF})
    MovJ(PickPOS.prep_pick)

    SetTFNo(Normal_TOOL_index) -- 恢复正常工具坐标系
end


local function Vision_1_Capture()
    -- 拍照找物料，判断是否启动散料。
    MovJ(PickPOS.prep_pick)
    -- 获取视觉工艺 0 的缓存区中的数据个数，并将其赋值给 count 变量。
    local count = VisionLen(Normal_VISION_NO)
    
    if count == 0 then
        SpreadMaterials()
        VisionTrig(Normal_VISION_NO, { timeout = 2 })
        count = VisionLen(Normal_VISION_NO) -- 重新读数
    end

    if count == 0 then
        print("Vision_1_Capture: 震动散料后仍未检测到物料")
        return false
    end

    return true
end


local function Main()
    Init()
    local picked = 0
    for i = 1, 20 do
        MovJ(PickPOS.prep_pick)
        if Vision_1_Capture() then
            Do1pick() -- 抓取物料后会清楚视觉缓存区数据的第一个点位
            Voffset()
            Do1place(PlrList[i])
            picked = picked + 1

        else
            print("缺少物料，抓取停止。")
            break
        end
        
    end
    print("本次共抓取 " .. picked .. " 次")
    VisionStop(Normal_VISION_NO)
    VisionStop(Offset_VISION_NO)
end

Main()