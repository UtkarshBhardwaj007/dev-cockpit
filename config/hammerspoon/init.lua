-- Dev Cockpit: trackpad pinch-to-zoom for Herdr panes (macOS).
--
-- A trackpad pinch is an AppKit gesture event. It reaches the terminal
-- emulator, never the pty, so Herdr and its plugins cannot observe it. This
-- bridge runs in Hammerspoon, watches gesture events, and forwards a synthetic
-- ctrl+alt+shift+F1/F2 chord to the frontmost terminal. Herdr binds those keys to
-- `pane zoom --on` / `--off`, so the command runs inside the focused pane and
-- targets that pane's own session through HERDR_SOCKET_PATH.
--
-- Pinch out (spread) zooms the focused Herdr pane; pinch in unzooms it.
-- Nothing happens unless a Ghostty or WezTerm window is frontmost, so pinches
-- in other apps are left alone.
--
-- Requires the Hammerspoon Accessibility permission (System Settings ->
-- Privacy & Security -> Accessibility). Without it the event tap observes
-- nothing and pinches keep their normal terminal behavior. Granting it requires
-- relaunching Hammerspoon: "Reload Config" reloads this Lua file but does not
-- restart the process, so it does not pick up the grant.
--
-- Press ctrl+alt+cmd+z at any time to print the bridge status in an alert.

local TERMINALS = {
  ["com.mitchellh.ghostty"] = "Ghostty",
  ["com.github.wez.wezterm"] = "WezTerm",
}

-- Direct modified function keys: Herdr maps these to pane zoom on/off.
--
-- F13/F14 look like the obvious choice, but Ghostty cannot encode them: its
-- legacy key table stops at F12 (no `ESC [ 25~` / `ESC [ 26~`), and it only
-- speaks xterm modifyOtherKeys, not the kitty keyboard protocol, so no CSI-u
-- fallback exists either. A ctrl+alt+shift+F1/F2 chord is encoded by Ghostty as
-- `ESC [ 1;8P` / `ESC [ 1;8Q`, which crossterm (and therefore Herdr) decodes to
-- F1/F2 with ctrl+alt+shift. Ghostty claims no F-key bindings by default, and
-- Option on a function key is treated as Alt regardless of macos-option-as-alt.
local ZOOM_IN_MODS = {"ctrl", "alt", "shift"}
local ZOOM_IN_KEY = "f1"
local ZOOM_OUT_MODS = {"ctrl", "alt", "shift"}
local ZOOM_OUT_KEY = "f2"

-- Deliberate-pinch detection: accumulate magnification until it clearly
-- exceeds trackpad noise, then act once and wait out a short cooldown.
local PINCH_THRESHOLD = 0.06
local COOLDOWN_SECONDS = 0.6
local IDLE_RESET_SECONDS = 0.4
local SHOW_ALERTS = false

local lastAction = 0
local lastEvent = 0
local accumulated = 0
local tap = nil
local retryTimer = nil

-- Always-visible notification used for startup and diagnostics.
local function notify(message, seconds)
  hs.alert.closeAll()
  hs.alert.show(message, nil, nil, seconds or 2)
end

-- Per-pinch feedback is opt-in so normal use stays quiet.
local function alert(message)
  if SHOW_ALERTS then
    notify(message, 0.4)
  end
end

local function frontmostTerminal()
  local app = hs.application.frontmostApplication()
  if not app then
    return nil
  end
  local bundle = app:bundleID()
  return bundle and TERMINALS[bundle] or nil
end

-- Forward the pinch to Herdr as a direct keybinding. The key travels through
-- the terminal to whichever Herdr pane has focus, so no session lookup is
-- needed and named sessions work without configuration.
local function sendZoomKey(mods, key, label)
  hs.eventtap.keyStroke(mods, key)
  alert(label)
  return true
end

-- Called for every trackpad gesture. Returns true to swallow the event so the
-- host terminal does not also act on it.
local function onGesture(event)
  if not frontmostTerminal() then
    return false
  end
  if event:getType(true) ~= hs.eventtap.event.types.magnify then
    return false
  end
  local details = event:getTouchDetails()
  local magnification = details and details.magnification
  if type(magnification) ~= "number" or magnification == 0 then
    return false
  end

  local now = hs.timer.secondsSinceEpoch()
  if now - lastEvent > IDLE_RESET_SECONDS then
    accumulated = 0
  end
  lastEvent = now
  accumulated = accumulated + magnification

  if now - lastAction < COOLDOWN_SECONDS then
    return true
  end
  if accumulated >= PINCH_THRESHOLD then
    accumulated = 0
    lastAction = now
    return sendZoomKey(ZOOM_IN_MODS, ZOOM_IN_KEY, "Herdr pane zoomed")
  elseif accumulated <= -PINCH_THRESHOLD then
    accumulated = 0
    lastAction = now
    return sendZoomKey(ZOOM_OUT_MODS, ZOOM_OUT_KEY, "Herdr pane unzoomed")
  end
  return true
end

local function accessibilityGranted(prompt)
  return hs.accessibilityState(prompt or false)
end

local function tapRunning()
  return tap ~= nil and tap:isEnabled()
end

-- (Re)create the event tap and report whether it is genuinely observing events.
-- hs.eventtap:start() returns the tap object rather than a status, and without
-- Accessibility CGEventTapCreate fails so the tap is never enabled; isEnabled()
-- is therefore the only real signal. This deliberately does not gate on
-- hs.accessibilityState(): macOS can keep reporting the old state for a process
-- that was already running when the grant was made, and the grant can also
-- arrive later, so the caller retries instead of giving up at load time.
local function startTap()
  if tapRunning() then
    return true
  end
  tap = hs.eventtap.new({hs.eventtap.event.types.gesture}, onGesture)
  tap:start()
  return tap:isEnabled()
end

-- Keep the bridge alive across logout and reboot.
hs.autoLaunch(true)

local function stopRetry()
  if retryTimer then
    retryTimer:stop()
    retryTimer = nil
  end
end

-- Start (or restart) the tap and announce the transition once. Granting
-- Accessibility after this config has loaded is the common case, and it must not
-- require a manual reload, so callers retry until the tap is really running.
local function ensureTap()
  if tapRunning() then
    return true
  end
  if not startTap() then
    return false
  end
  stopRetry()
  notify("Dev Cockpit: pinch zoom for Herdr enabled", 1)
  return true
end

if not ensureTap() then
  notify("Dev Cockpit: pinch zoom needs Accessibility. Grant Hammerspoon "
    .. "Accessibility (System Settings > Privacy & Security > Accessibility); "
    .. "it will start on its own within a few seconds. If it does not, quit and "
    .. "reopen Hammerspoon. Press ctrl+alt+cmd+z to re-check.", 10)
  retryTimer = hs.timer.doEvery(3, function()
    ensureTap()
  end)
end

-- Fires when macOS changes Hammerspoon's Accessibility state.
hs.accessibilityStateCallback = function()
  ensureTap()
end

-- Manual diagnostic: press ctrl+alt+cmd+z to see why a pinch is or is not
-- working without having to guess.
hs.hotkey.bind({"ctrl", "alt", "cmd"}, "z", function()
  local parts = {}
  parts[#parts + 1] = tapRunning() and "tap running" or "tap NOT running"
  parts[#parts + 1] = accessibilityGranted(false) and "Accessibility granted" or "Accessibility MISSING"
  local terminal = frontmostTerminal()
  parts[#parts + 1] = terminal and ("frontmost: " .. terminal) or "frontmost: not Ghostty/WezTerm"
  if not tapRunning() then
    parts[#parts + 1] = "quit and reopen Hammerspoon after granting Accessibility"
  end
  notify("Dev Cockpit pinch zoom: " .. table.concat(parts, ", "), 4)
end)
