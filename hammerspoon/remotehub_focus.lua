-- remotehub_focus.lua — 遥控器「跳输入框 / 切换后焦点修复 / 点击焦点元素」后端 v1.1 (2026-10-10)
-- ------------------------------------------------------------------
-- v1.1（10-10 20:2x）: 新增 clickFocused() —— 点击「当前键盘焦点元素」
--   （AXPress 主路径: 自身或向上 ≤6 层找最近支持者; 全不支持时坐标鼠标点击兜底）。
--   背景: WorkBuddy/Electron 的 TAB 可达元素（任务列表条目等）不响应合成 ENTER
--   （组件未实现键盘激活），但 AXPress 实测与真实点击等效（20:1x 任务切换往返双验证）。
--   调用: hs -c 'return dofile("...").clickFocused()'（key_bridge v1.9 CLICK 动作）。
-- ------------------------------------------------------------------
-- 主源: remote-hub/hammerspoon/remotehub_focus.lua → 部署副本 ~/.hammerspoon/remotehub_focus.lua
-- 调用方（key_bridge.py / AppPicker.app，经 Hammerspoon 自带 hs CLI）:
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").focusInput()'   -- 跳输入框
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").assistLater()'  -- 切换后修复（+0.45s 自行调度）
--   hs -c 'return dofile("/Users/username/.hammerspoon/remotehub_focus.lua").focusWindow()'  -- 立即修复（调试）
--
-- 背景（2026-10-10 实证）:
--   · Chromium/Electron 系（WorkBuddy/Obsidian）AX 树遍历不可靠（后台更甚）—— 真实
--     元素要用坐标 hit-test（systemWide:elementAtPosition）才拿得到;
--   · 微信（com.tencent.xinWeChat）内容层完全没有 AX（24 点探测全 nil + 5 节点树）,
--     本脚本对其只能做到窗口聚焦修复（阶段 1）。
-- 策略（focusInput）: ① 窗口聚焦修复（unmin/raise/main/focused）→ ② 缓存点（曾命中过
--   的窗口比例坐标）→ ③ 坐标网格（底部输入区优先, 聊天/编辑器通吃）→ ④ 可见树遍历
--   （对 Safari 等“树完整”的补救）→ ⑤ 全失败仅报 NOEDIT（窗口修复仍已生效）。
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

  -- ① 窗口聚焦修复（总是先做; 对微信等无内容 AX 的应用即最终效果）
  focusWindowOf(w)

  -- ② 缓存点
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

  -- ③ 坐标网格
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

  -- ④ 树遍历
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
    return string.format("NOEDIT %s win=%.0fx%.0f (窗口已修复, 未找到输入框)", aname, size.w, size.h)
  end

  -- ⑤ 设焦点 + 读回
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

return M
