-- remotehub_focus.lua — 遥控器「跳输入框 / 切换后焦点修复 / 点击焦点元素 / 鼠标模式执行器 / 模式 HUD / 设备切换 HUD」后端 v1.6 (2026-10-14)
-- ------------------------------------------------------------------
-- v1.6（10-14 深挖修复 —— 承「兜底点击后仍不灵」复查）: 两个根因：
--   ① 遮挡: 目标 app 窗口未必在 z 序最顶（现场实例=抖音直播窗压在 WorkBuddy 上）,
--      合成点击会落在遮挡窗口上 → 新增 ensureFrontApp(): app:activate() + z 序校验
--      （≤3 次重试, 每次 120ms）—— 也是「点进输入框后打字真的进得去」的前提
--      （键盘事件按 frontmost 分发）;
--   ② 坐标: v1.5 的 0.92 比例偏低（实测落在输入框下方按钮行）→ 改「距窗底固定
--      105px」（WorkBuddy 输入框文字行实测值; 比例坐标对窗口高度变化敏感, 固定
--      像素距底对「底部输入区」的聊天类 UI 更稳）。
--   返回串新增 front=ok|fail 诊断字段（前台提升结果）。
--   实测验证（2026-10-14 03:3x）: activate+click(956,767) → 字符注入落入输入框 ✓。
-- ------------------------------------------------------------------
-- v1.5（10-14 NOEDIT 兜底点击 —— 承用户反馈「焦点聚焦键不灵」）: focusInput 五段策略
--   全失败（NOEDIT, 即微信等无内容 AX 的应用）时, 不再直接报错, 改为「底部中央
--   兜底点击」(窗口比例 0.5, 0.92 —— 聊天/评论类输入区几何假设; 微信实测输入框
--   文本区在窗口 88%-96% 高度带); 点击后恢复用户鼠标位置。返回
--   "NOEDIT+CLICK@x,y ..."。背景: 微信内容层完全没有 AX（见下 2026-10-10 实证）,
--   缓存/网格/树三段对它是空转 —— 坐标点击是唯一可用的聚焦手段。
--   配套: T1 voice_fwd v2.8（鼠标模式内 #41 放行, 本兜底在键盘/鼠标模式均可达）。
-- ------------------------------------------------------------------
-- v1.4（10-13 电源键连击切换设备）: 新增 switchHud(name) —— 设备切换 HUD（hs.alert
--   浮层「🎯 已切到 X」+ 提示音; ATV/macOS/Windows 名称映射）。调用方 =
--   key_bridge v1.15 TARGET:SWITCH:ATV|MAC|WIN; T1 侧 voice_fwd v2.7 电源键连击
--   提交后发送（切到 atv 发旧目标端 / 切到 mac·win 发新目标端）。纯新增 API。
-- ------------------------------------------------------------------
-- v1.1（10-10 20:2x）: 新增 clickFocused() —— 点击「当前键盘焦点元素」
--   （AXPress 主路径: 自身或向上 ≤6 层找最近支持者; 全不支持时坐标鼠标点击兜底）。
--   背景: WorkBuddy/Electron 的 TAB 可达元素（任务列表条目等）不响应合成 ENTER
--   （组件未实现键盘激活），但 AXPress 实测与真实点击等效（20:1x 任务切换往返双验证）。
--   调用: hs -c 'return dofile("...").clickFocused()'（key_bridge v1.9 CLICK 动作）。
-- ------------------------------------------------------------------
-- v1.3（10-13 实测反馈修复轮）: 新增 mouseHud(mode) —— 鼠标/键盘模式切换 HUD 提示
--   （hs.alert 大字号浮层「🖱 鼠标模式 / ⌨ 键盘模式」+ 开/关区分提示音; 治用户反馈
--   「按了不知道生效没有」）。调用方 = key_bridge v1.14 MOUSE:MODE:ON|OFF; T1 侧
--   voice_fwd v2.6 在切换 / 模式内单按 #41 时主动发送。纯新增 API, 不影响执行器语义。
-- ------------------------------------------------------------------
-- v1.2（10-13 12:5x）: 新增鼠标模式执行器（key_bridge MOUSE:* 动作后端）——
--   方向键 → 滑行移动光标（60Hz 定时 + 线性加速, 按住越久越快; 1.2s 无刷新自动停,
--   上游断链不失控）; OK → 光标处左/右键点击; 音量键 → 连续滚动; MOUSE:OFF 全停。
--   ⚠ 状态挂 _G.REMOTEHUB_MOUSE 全局单例: hs -c 每次重新 dofile, 状态与定时器
--   必须跨调用存活（勿改回 local）。纯新增 API, 不影响既有 focusInput/clickFocused。
-- ------------------------------------------------------------------
-- 主源: remote-hub/hammerspoon/remotehub_focus.lua → 部署副本 ~/.hammerspoon/remotehub_focus.lua
-- 调用方（key_bridge.py / AppPicker.app，经 Hammerspoon 自带 hs CLI）:
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").focusInput()'   -- 跳输入框
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").assistLater()'  -- 切换后修复（+0.45s 自行调度）
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").focusWindow()'  -- 立即修复（调试）
--   hs -c 'return dofile("...").mouseStatus()'  -- 鼠标通道自检（位置/速度/方向/定时器）
--   hs -c 'return dofile("...").mouseHud("on")' -- 模式提示 HUD（调试; "on"/"off"）
--   hs -c 'return dofile("...").switchHud("atv")' -- 设备切换 HUD（调试; "atv"/"mac"/"win"）
--
-- 背景（2026-10-10 实证）:
--   · Chromium/Electron 系（WorkBuddy/Obsidian）AX 树遍历不可靠（后台更甚）—— 真实
--     元素要用坐标 hit-test（systemWide:elementAtPosition）才拿得到;
--   · 微信（com.tencent.xinWeChat）内容层完全没有 AX（24 点探测全 nil + 5 节点树）,
--     本脚本对其只能做到窗口聚焦修复（阶段 1）。
-- 策略（focusInput）: ① 窗口聚焦修复（unmin/raise/main/focused）→ ② 前台提升（v1.6,
--   activate + z 序校验 ≤3 次）→ ③ 缓存点（曾命中过的窗口比例坐标）→ ④ 坐标网格
--   （底部输入区优先, 聊天/编辑器通吃）→ ⑤ 可见树遍历（对 Safari 等“树完整”的补救）
--   → ⑥ 全失败（v1.5+）: 底部中央兜底点击（0.5, 距窗底 105px）, 报 NOEDIT+CLICK@x,y；
--   前台提升失败（front=fail）时跳过点击（防误点遮挡弹窗按钮）。
-- 缓存: ~/.hammerspoon/remotehub_focus_cache.json（bundleID → {fx, fy} 窗口比例坐标）。
-- 归属: 权限走 Hammerspoon.app 的辅助功能授权（hs.accessibilityState()=true, 无需
--   新 TCC）; 修改本文件不涉及任何签名/授权（纯脚本）。
-- ------------------------------------------------------------------
local M = {}

local sw = hs.axuielement.systemWideElement()
local HOME = os.getenv("HOME") or "/Users/username"
local CACHE_PATH = HOME .. "/.hammerspoon/remotehub_focus_cache.json"

local EDITABLE = {
  AXTextArea = true,
  AXTextField = true,
  AXSearchField = true,
  AXComboBox = true,
  AXSecureTextField = true,
}

-- 探测网格（窗口比例）: 行序=底部输入区优先（聊天类）→ 中部（编辑器类）→ 顶部;
-- 列序=横向中位优先，兼顾左右分栏布局。
local GRID_X = { 0.5, 0.62, 0.74, 0.38, 0.86, 0.26 }
local GRID_Y = { 0.85, 0.82, 0.88, 0.78, 0.90, 0.72, 0.62, 0.50, 0.40, 0.30, 0.20, 0.12 }

local function attr(el, name)
  if not el then return nil end
  local ok, v = pcall(function() return el:attributeValue(name) end)
  return ok and v or nil
end

local function roleOf(el)
  return attr(el, "AXRole")
end

local function isEditable(el)
  local r = roleOf(el)
  return r ~= nil and EDITABLE[tostring(r)] == true
end

local function hit(x, y)
  local ok, el = pcall(function() return sw:elementAtPosition(x, y) end)
  if ok and el then return el end
  return nil
end

local function frameOf(w)
  local pos = attr(w, "AXPosition")
  local size = attr(w, "AXSize")
  if pos and size and pos.x ~= nil and pos.y ~= nil and size.w ~= nil and size.h ~= nil then
    return pos, size
  end
  return nil, nil
end

local function loadCache()
  local ok, data = pcall(function()
    local f = io.open(CACHE_PATH, "r")
    if not f then return nil end
    local s = f:read("*a")
    f:close()
    if not s or s == "" then return nil end
    return hs.json.decode(s)
  end)
  if ok and type(data) == "table" then return data end
  return {}
end

local function saveCache(t)
  pcall(function()
    local f = io.open(CACHE_PATH, "w")
    if f then
      f:write(hs.json.encode(t))
      f:close()
    end
  end)
end

local function pickWindow(ae)
  local w = attr(ae, "AXFocusedWindow") or attr(ae, "AXMainWindow")
  if w then return w end
  local ws = attr(ae, "AXWindows")
  if ws and type(ws) == "table" and #ws > 0 then return ws[1] end
  return nil
end

local function pickWindowRetry(ae, tries)
  for _ = 1, (tries or 4) do
    local w = pickWindow(ae)
    if w then return w end
    hs.timer.usleep(150000)
  end
  return nil
end

-- v1.6: 把目标 app 提升到 z 序最前（合成点击与键盘焦点的前提——被遮挡时否则点到
-- 别的窗口、键盘事件也进不去）。返回 (raised, tries)；失败不阻塞主流程, 由调用方
-- 在返回串标注 front= 供诊断。
local function ensureFrontApp(app, bid)
  if not app then return false, 0 end
  for i = 1, 3 do
    pcall(function() app:activate() end)
    hs.timer.usleep(150000)
    local ws = hs.window.orderedWindows()
    local top = ws and ws[1] or nil
    if not top then top = hs.window.frontmostWindow() end
    local tapp = top and top:application()
    if tapp and tostring(tapp:bundleID()) == tostring(bid) then
      return true, i
    end
  end
  return false, 3
end

-- 窗口聚焦修复（不依赖可编辑元素）: 解除最小化 + 置 main + raise + 置焦点
local function focusWindowOf(w)
  local fixes = {}
  if attr(w, "AXMinimized") == true then
    pcall(function() w:setAttributeValue("AXMinimized", false) end)
    fixes[#fixes+1] = "unmin"
  end
  pcall(function() w:setAttributeValue("AXMain", true) end)
  pcall(function() w:performAction("AXRaise") end)
  pcall(function() w:setAttributeValue("AXFocused", true) end)
  fixes[#fixes+1] = "raise+main+focus"
  return table.concat(fixes, "+")
end

-- 树遍历找首个可编辑（深度/预算封顶; 对 Safari 等有效, 对 Chromium 空转）
local function treeFindEditable(rootEl)
  local budget = { n = 400 }
  local found = nil
  local function walk(el, depth)
    if found or depth > 14 or budget.n <= 0 then return end
    budget.n = budget.n - 1
    if isEditable(el) then found = el return end
    local ch = attr(el, "AXChildren")
    if ch and type(ch) == "table" then
      for _, c in ipairs(ch) do
        walk(c, depth + 1)
        if found then return end
      end
    end
  end
  walk(rootEl, 0)
  return found
end

-- ============ 对外 API ============

-- 跳输入框: 修复窗口 + 聚焦首个可编辑元素
function M.focusInput()
  local app = hs.application.frontmostApplication()
  if not app then return "ERR no-app" end
  local aname = tostring(app:name() or "?")
  local bid = tostring(app:bundleID() or aname)
  local ae = hs.axuielement.applicationElement(app)
  if not ae then return "ERR no-app-element " .. aname end
  local w = pickWindow(ae)
  if not w then return "ERR no-window " .. aname end
  local pos, size = frameOf(w)
  if not pos then return "ERR no-frame " .. aname end

  -- ① 窗口聚焦修复（总是先做; 含 unmin——须在 z 序校验前, 否则最小化窗口不在 z 序里）。
  --    对微信等无内容 AX 的应用即最终效果。
  focusWindowOf(w)

  -- ② v1.6: 前台提升——确保目标 app 在 z 序最顶（否则合成点击落到遮挡窗口 /
  --    键盘事件进不去）。放在窗口修复之后: unmin 完成后再校验才有意义。
  local raised = ensureFrontApp(app, bid)

  -- ③ 缓存点
  local el, fx, fy, src = nil, nil, nil, nil
  local cache = loadCache()
  local c = cache[bid]
  if type(c) == "table" and c.fx and c.fy then
    local x = pos.x + size.w * c.fx
    local y = pos.y + size.h * c.fy
    local e2 = hit(x, y)
    if isEditable(e2) then
      el, fx, fy, src = e2, c.fx, c.fy, "cache"
    end
  end

  -- ④ 坐标网格
  if not el then
    for _, gy in ipairs(GRID_Y) do
      for _, gx in ipairs(GRID_X) do
        local x = pos.x + size.w * gx
        local y = pos.y + size.h * gy
        local ymax = pos.y + size.h - 10
        if y > ymax then y = ymax end
        local e2 = hit(x, y)
        if isEditable(e2) then
          el, fx, fy, src = e2, gx, gy, "grid"
          break
        end
      end
      if el then break end
    end
  end

  -- ⑤ 树遍历
  if not el then
    local e2 = treeFindEditable(w)
    if isEditable(e2) then
      el, src = e2, "tree"
      local ep = attr(e2, "AXPosition")
      local es = attr(e2, "AXSize")
      if ep and es and ep.x and ep.y then
        fx = (ep.x + (es.w or 0) / 2 - pos.x) / size.w
        fy = (ep.y + (es.h or 0) / 2 - pos.y) / size.h
        fx = math.max(0.05, math.min(0.95, fx))
        fy = math.max(0.05, math.min(0.95, fy))
      end
    end
  end

  if not el then
    -- ★ v1.6 NOEDIT 兜底: 底部中央点击。y = 距窗底 105px（v1.5 的 0.92 比例实测偏低,
    --   落在输入框下方按钮行; 105px = WorkBuddy 输入框文字行实测, 微信等聊天类亦大致
    --   同区间; 固定像素距底对窗口高度变化比比例坐标稳）。点击后恢复用户鼠标位置。
    local bx = pos.x + size.w * 0.5
    local by = pos.y + size.h - 105
    local ymin = pos.y + size.h * 0.5
    if by < ymin then by = ymin end
    local ymax = pos.y + size.h - 4
    if by > ymax then by = ymax end
    if not raised then
      -- 前台提升失败（≤3 次 activate 后 z 序仍未确认）: 跳过点击——疑似弹窗/异常
      -- 遮挡, 盲目点击恐误中他人按钮（如授权弹窗）; 如实回报供诊断。
      return string.format("NOEDIT@%.0f,%.0f %s win=%.0fx%.0f front=fail-skip (前台提升失败, 未点击)",
        bx, by, aname, size.w, size.h)
    end
    local mob = hs.mouse.absolutePosition()
    hs.eventtap.leftClick(hs.geometry.point(bx, by))
    hs.timer.usleep(80000)                        -- 80ms 让点击落地再恢复光标
    if mob then hs.mouse.absolutePosition(mob) end
    return string.format("NOEDIT+CLICK@%.0f,%.0f %s win=%.0fx%.0f front=ok (未找到输入框, 已兜底点击)",
      bx, by, aname, size.w, size.h)
  end

  -- ⑥ 设焦点 + 读回
  local before = attr(el, "AXFocused")
  if before ~= true then
    local okSet = pcall(function() return el:setAttributeValue("AXFocused", true) end)
    if not okSet then
      return string.format("FAIL-set %s role=%s fx=%.2f fy=%.2f", aname, tostring(roleOf(el)), fx or -1, fy or -1)
    end
  end
  local after = attr(el, "AXFocused")

  -- 成功则更新缓存（fx/fy 已知时）
  if (after == true or before == true) and fx and fy then
    cache[bid] = { fx = fx, fy = fy }
    saveCache(cache)
  end

  return string.format("OK %s role=%s fx=%.2f fy=%.2f src=%s before=%s after=%s",
    aname, tostring(roleOf(el)), fx or -1, fy or -1, tostring(src), tostring(before), tostring(after))
end

-- 立即做窗口聚焦修复（前台应用）
local function focusWindowNow()
  local app = hs.application.frontmostApplication()
  if not app then return "ERR no-app" end
  local aname = tostring(app:name() or "?")
  local ae = hs.axuielement.applicationElement(app)
  if not ae then return "ERR no-app-element " .. aname end
  local w = pickWindowRetry(ae, 4)
  if not w then return "ERR no-window " .. aname end
  local fixes = focusWindowOf(w)
  return string.format("OK winfix %s [%s]", aname, fixes)
end

function M.focusWindow()
  return focusWindowNow()
end

-- 调度式修复: 立即返回, +0.45s 后执行（供应用切换后调用, 不阻塞调用方）
function M.assistLater()
  hs.timer.doAfter(0.45, function()
    local ok, r = pcall(focusWindowNow)
    print("remotehub_focus.assist: " .. tostring(ok and r or r))
  end)
  return "scheduled"
end

-- ============ v1.1: 点击焦点元素（key_bridge CLICK 动作后端） ============

-- 点击「当前键盘焦点元素」，四段策略:
--   ① 自身支持 AXPress → 直接 press（多数情况，如任务条目 AXButton）
--   ② 直接子元素支持 AXPress（壳容器场景，如 Artifact tab 外壳 AXGroup → 子 AXRadioButton）
--   ③ 向上 ≤6 层找最近支持者
--   ④ 坐标兜底: 焦点元素中心鼠标左键点击（尺寸门槛 w>8,h>4，剔除 1px 垃圾坐标防误点）
-- 返回详情字符串（进 key_bridge 日志: OK press <role> t=<label> via=<路径> / OK click@x,y / FAIL ...）
function M.clickFocused()
  local el = attr(sw, "AXFocusedUIElement")
  if not el then return "NOFOCUS (无焦点元素)" end

  local function hasPress(e)
    if not e then return false end
    local acts = nil
    pcall(function() acts = e:actionNames() end)
    if type(acts) ~= "table" then return false end
    for _, a in ipairs(acts) do
      if tostring(a) == "AXPress" then return true end
    end
    return false
  end

  local found, how = nil, nil
  -- ① 自身
  if hasPress(el) then found, how = el, "self" end
  -- ② 直接子元素（壳容器场景: 如 Artifact tab 外壳 AXGroup → 子 AXRadioButton）
  if not found then
    local ch = attr(el, "AXChildren")
    if type(ch) == "table" then
      for _, c in ipairs(ch) do
        if hasPress(c) then found, how = c, "child" break end
      end
    end
  end
  -- ③ 向上 ≤6 层
  if not found then
    local cur, depth = attr(el, "AXParent"), 1
    while cur and depth <= 6 do
      if hasPress(cur) then found, how = cur, "up" .. depth break end
      cur = attr(cur, "AXParent")
      depth = depth + 1
    end
  end

  if found then
    local role = tostring(attr(found, "AXRole"))
    local label = ""
    local tv = attr(found, "AXTitle")
    local dv = attr(found, "AXDescription")
    if type(tv) == "string" and tv ~= "" then label = tv
    elseif type(dv) == "string" and dv ~= "" then label = dv end
    local okp = pcall(function() return found:performAction("AXPress") end)
    if okp then
      return string.format("OK press %s t=%s via=%s", role, label:sub(1, 36), how)
    end
  end

  -- ④ 坐标兜底: 点击焦点元素中心（尺寸门槛: 剔除 1px 垃圾坐标, 防误点）
  local pos = attr(el, "AXPosition")
  local size = attr(el, "AXSize")
  if pos and size and pos.x and pos.y and size.w and size.h and size.w > 8 and size.h > 4 then
    local x = pos.x + size.w / 2
    local y = pos.y + size.h / 2
    local okc = pcall(function()
      hs.eventtap.leftClick(hs.geometry.point(x, y))
    end)
    if okc then
      return string.format("OK click@%.0f,%.0f (坐标兜底)", x, y)
    end
  end

  return "FAIL (无 AXPress 且无有效坐标) role=" .. tostring(attr(el, "AXRole"))
end

-- ============ v1.2: 鼠标模式执行器（key_bridge MOUSE:* 动作后端） ============
-- 滑行参数（实测可调; px/s 与 px/s²）:
-- 速度自 0 线性加速（无 base）——轻点=精准微调（0.3s ≈ 27px 实测）, 按住≈2s 横扫全屏。
local MOVE_ACCEL  = 700     -- 线性加速度
local MOVE_MAX    = 1600    -- 速度上限
local SCROLL_PX   = 15      -- 每 tick 滚动像素（60Hz -> 900 px/s）
local SCROLL_SIGN = 1       -- 滚动方向翻转位（+1 = up 向上滚; 实测反向改 -1）
local TICK        = 1 / 60
local STALE       = 1.2     -- 方向无刷新超时秒数（T1 连发节奏 0.12s 的余量）

local MDIR = { up = { 0, -1 }, down = { 0, 1 }, left = { -1, 0 }, right = { 1, 0 } }

local S = rawget(_G, "REMOTEHUB_MOUSE")
if not S then
  S = { move = {}, scroll = {}, speed = 0, timer = nil }
  rawset(_G, "REMOTEHUB_MOUSE", S)
end

local function nowT()
  return hs.timer.secondsSinceEpoch()
end

local function screenBounds()
  local minx, miny, maxx, maxy
  for _, sc in ipairs(hs.screen.allScreens()) do
    local f = sc:fullFrame()
    if not minx or f.x < minx then minx = f.x end
    if not miny or f.y < miny then miny = f.y end
    if not maxx or f.x + f.w > maxx then maxx = f.x + f.w end
    if not maxy or f.y + f.h > maxy then maxy = f.y + f.h end
  end
  return minx or 0, miny or 0, maxx or 2560, maxy or 1440
end

local function nactive(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

local function stopTimer()
  if S.timer then
    S.timer:stop()
    S.timer = nil
  end
  S.speed = 0
end

local function tick()
  local t = nowT()
  for d, ts in pairs(S.move) do
    if t - ts > STALE then S.move[d] = nil end
  end
  for d, ts in pairs(S.scroll) do
    if t - ts > STALE then S.scroll[d] = nil end
  end
  if nactive(S.move) == 0 and nactive(S.scroll) == 0 then
    stopTimer()
    return
  end
  -- 滑行移动（多方向叠加 -> 天然支持斜向; 屏幕包围盒夹取防 warp 出界）
  if nactive(S.move) > 0 then
    S.speed = math.min(MOVE_MAX, (S.speed or 0) + MOVE_ACCEL * TICK)
    local vx, vy = 0, 0
    for d in pairs(S.move) do
      vx = vx + MDIR[d][1]
      vy = vy + MDIR[d][2]
    end
    local p = hs.mouse.absolutePosition()
    local minx, miny, maxx, maxy = screenBounds()
    local nx = math.max(minx + 1, math.min(maxx - 2, p.x + vx * S.speed * TICK))
    local ny = math.max(miny + 1, math.min(maxy - 2, p.y + vy * S.speed * TICK))
    hs.mouse.absolutePosition({ x = nx, y = ny })
  else
    S.speed = 0
  end
  -- 连续滚动（音量键; 可与移动并行）
  if nactive(S.scroll) > 0 then
    local dy = 0
    if S.scroll.up then dy = dy + SCROLL_PX end
    if S.scroll.down then dy = dy - SCROLL_PX end
    if dy ~= 0 then
      pcall(hs.eventtap.scrollWheel, { 0, dy * SCROLL_SIGN }, {}, "pixel")
    end
  end
end

local function ensureTimer()
  if not S.timer and (nactive(S.move) > 0 or nactive(S.scroll) > 0) then
    S.timer = hs.timer.doEvery(TICK, tick)
  end
end

function M.mouseStart(dir)
  if not MDIR[dir] then return "ERR bad-dir " .. tostring(dir) end
  S.move[dir] = nowT()
  ensureTimer()
  return string.format("OK move %s on", dir)
end

function M.mouseStop(dir)
  S.move[dir] = nil
  if nactive(S.move) == 0 and nactive(S.scroll) == 0 then stopTimer() end
  return "OK move " .. tostring(dir) .. " off"
end

function M.mouseStopAll()
  S.move = {}
  S.scroll = {}
  stopTimer()
  return "OK all stopped"
end

function M.mouseClick(btn)
  local p = hs.mouse.absolutePosition()
  local ok, err
  if btn == "right" then
    ok, err = pcall(hs.eventtap.rightClick, p, 0.04)
  else
    ok, err = pcall(hs.eventtap.leftClick, p, 0.04)
  end
  if ok then
    return string.format("OK %s-click @%.0f,%.0f", btn or "left", p.x, p.y)
  end
  return "FAIL click: " .. tostring(err)
end

function M.scrollStart(dir)
  if dir ~= "up" and dir ~= "down" then return "ERR bad-scroll " .. tostring(dir) end
  S.scroll[dir] = nowT()
  ensureTimer()
  return "OK scroll " .. dir .. " on"
end

function M.scrollStop(dir)
  S.scroll[dir] = nil
  if nactive(S.move) == 0 and nactive(S.scroll) == 0 then stopTimer() end
  return "OK scroll " .. tostring(dir) .. " off"
end

function M.mouseStatus()
  local p = hs.mouse.absolutePosition()
  local m, s = {}, {}
  for d in pairs(S.move) do m[#m + 1] = d end
  for d in pairs(S.scroll) do s[#s + 1] = d end
  return string.format("pos=%.0f,%.0f v=%.0f move=[%s] scroll=[%s] timer=%s",
    p.x, p.y, S.speed or 0, table.concat(m, ","), table.concat(s, ","),
    S.timer and "on" or "off")
end

-- ============ v1.3: 模式切换 HUD（key_bridge v1.14 MOUSE:MODE:ON|OFF 后端） ============
-- 设计: 大字号深底浮层 1.1s 自动消失（任何桌面背景下可读）; 开/关配不同提示音
--   （盲操可辨 —— 不看屏也知道切没切）; closeAll 防连按堆叠。纯 UI, 不动模式状态。
local HUD_TEXT_ON   = "🖱 鼠标模式"
local HUD_TEXT_OFF  = "⌨ 键盘模式"
local HUD_SOUND_ON  = "Glass"    -- nil 禁用（系统音, hs.sound 找不到则静默跳过）
local HUD_SOUND_OFF = "Pop"
local HUD_SECONDS   = 1.1
local HUD_STYLE = {
  textSize = 44,
  radius = 18,
  strokeWidth = 0,
  padding = 26,
  fillColor = { red = 0.08, green = 0.08, blue = 0.10, alpha = 0.88 },
  textColor = { white = 1, alpha = 1 },
}

local function playSound(name)
  if not name then return end
  pcall(function()
    local s = hs.sound.getByName(name)
    if s then s:play() end
  end)
end

function M.mouseHud(mode)
  local on = tostring(mode):lower() == "on"
  local scr = hs.mouse.getCurrentScreen() or hs.screen.mainScreen()
  local ok, err = pcall(function()
    hs.alert.closeAll()
    hs.alert.show(on and HUD_TEXT_ON or HUD_TEXT_OFF, HUD_STYLE, scr, HUD_SECONDS)
  end)
  playSound(on and HUD_SOUND_ON or HUD_SOUND_OFF)
  if ok then
    return "OK hud " .. (on and "on" or "off")
  end
  return "FAIL hud: " .. tostring(err)
end

-- ============ v1.4: 设备切换 HUD（key_bridge v1.15 TARGET:SWITCH:<NAME> 后端） ============
-- 设计: 与模式 HUD 同款浮层（不同文案/图标）——“已切到 X” 让用户知道电源键连击生效。
local SWITCH_NAMES = { atv = "ATV", mac = "macOS", win = "Windows" }

function M.switchHud(name)
  local key = tostring(name):lower()
  local nm = SWITCH_NAMES[key] or tostring(name)
  local scr = hs.mouse.getCurrentScreen() or hs.screen.mainScreen()
  local ok, err = pcall(function()
    hs.alert.closeAll()
    hs.alert.show("🎯 已切到 " .. nm, HUD_STYLE, scr, HUD_SECONDS)
  end)
  playSound(HUD_SOUND_ON)
  if ok then
    return "OK hud switch:" .. key
  end
  return "FAIL hud switch: " .. tostring(err)
end

return M
