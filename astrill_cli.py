#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Astrill VPN CLI for Windows
===========================
Control the Astrill desktop client (v3.x) without an official CLI:
  * status      - is the VPN tunnel up? (read from the Windows routing table)
  * connect     - click the ON/OFF button in the Astrill main window
  * disconnect  - click the ON/OFF button in the Astrill main window

Everything is located dynamically at run time:
  * the Astrill window is found by process name (PID may change)
  * the ON/OFF button is found by colour (orange = disconnected) inside a
    screenshot of the window, so window position/size may change freely.

Requires: Python 3.8+, Windows 10+.  No third-party packages.
"""

import argparse
import ctypes
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
PROC_NAME = "astrill.exe"
WINDOW_TITLE = "Astrill"
WINDOW_CLASS = "Window"

# colour signature of the "connect" button (Astrill orange #F74100-ish)
BUTTON_ORANGE = (190, 130, 70, 90)  # r_min, g_max, b_max, (r-g)_min

# fallback: relative position of the button centre inside the window
# (measured at 360x453 physical px window; 0.5 / 0.30 of width / height)
FALLBACK_BTN = (0.503, 0.300)

# after clicking, poll the route table for up to this long (seconds)
CONNECT_TIMEOUT = 40
POLL_INTERVAL = 1.0

SW_RESTORE = 9
GA_ROOT = 2

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def set_dpi_aware():
    """Make the process per-monitor DPI aware so screen coords = physical px."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        return True
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return True
        except Exception:
            return False


def win_text(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def win_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def win_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def find_astrill_pids():
    """PIDs of every running astrill.exe."""
    pids = []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {PROC_NAME}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return pids
    for line in out.splitlines():
        m = re.match(rf'"{PROC_NAME}","(\d+)"', line.strip())
        if m:
            pids.append(int(m.group(1)))
    return pids


def find_astrill_window():
    """Find the Astrill main window (top-level, pid match).
    Returns hwnd or None.  Prefers a visible window titled 'Astrill'."""
    pids = set(find_astrill_pids())
    if not pids:
        return None
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            title = win_text(hwnd)
            cls = win_class(hwnd)
            if title == WINDOW_TITLE or cls == WINDOW_CLASS:
                found.append((hwnd, title, cls))
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return None
    # prefer exact title match
    for hwnd, title, cls in found:
        if title == WINDOW_TITLE:
            return hwnd
    return found[0][0]


def ensure_astrill_running():
    """Start astrill.exe if it is not running. Returns True if it is running after."""
    if find_astrill_pids():
        return True
    install = None
    try:
        out = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\Astrill", "/v", "InstallPath"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        m = re.search(r"InstallPath\s+REG_SZ\s+(.+)$", out, re.M)
        if m:
            install = m.group(1).strip()
    except Exception:
        pass
    candidates = []
    if install:
        # InstallPath 通常是安装目录(带尾斜杠),也可能是 exe 路径,两种都试
        candidates.append(os.path.join(install, "astrill.exe"))
        candidates.append(install)
    candidates += [r"C:\Program Files (x86)\Astrill\astrill.exe",
                   r"C:\Program Files\Astrill\astrill.exe"]
    exe = next((p for p in candidates if p and os.path.exists(p)), None)
    if not exe:
        return False
    try:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except Exception:
        return False
    for _ in range(20):
        time.sleep(0.5)
        if find_astrill_pids():
            return True
    return False


def show_window(hwnd):
    """Make the window visible & restore if needed."""
    if not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)


def capture_rect(x, y, w, h):
    """BitBlt the screen region into a list of rows of (r, g, b).  Physical px."""
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    px = []
    stride = w * 4
    raw = bytes(buf)
    for y in range(h):
        row = []
        base = y * stride
        for x in range(w):
            o = base + x * 4
            row.append((raw[o + 2], raw[o + 1], raw[o]))
        px.append(row)
    return px


def is_orange(r, g, b):
    return (r >= BUTTON_ORANGE[0] and g <= BUTTON_ORANGE[1] and b <= BUTTON_ORANGE[2]
            and r - g >= BUTTON_ORANGE[3])


def largest_orange_blob(px, y_ratio=0.55):
    """Return (cx, cy, count) of the biggest connected orange region in the
    top `y_ratio` of the image, or None.  The ON/OFF button sits around 30%
    height; small orange icons at the bottom of the window are excluded."""
    h = len(px)
    w = len(px[0])
    limit_y = max(1, int(h * y_ratio))
    visited = [[False] * w for _ in range(h)]
    best = None  # (count, minx, miny, maxx, maxy)
    for sy in range(limit_y):
        for sx in range(w):
            if visited[sy][sx] or not is_orange(*px[sy][sx]):
                continue
            stack = [(sx, sy)]
            visited[sy][sx] = True
            n = 0
            minx = maxx = sx
            miny = maxy = sy
            while stack:
                cx, cy = stack.pop()
                n += 1
                if cx < minx: minx = cx
                if cx > maxx: maxx = cx
                if cy < miny: miny = cy
                if cy > maxy: maxy = cy
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and is_orange(*px[ny][nx]):
                        visited[ny][nx] = True
                        stack.append((nx, ny))
            if n >= 100 and (best is None or n > best[0]):
                best = (n, minx, miny, maxx, maxy)
    if best is None:
        return None
    n, minx, miny, maxx, maxy = best
    return ((minx + maxx) // 2, (miny + maxy) // 2, n)


def window_belongs_to(hwnd, point):
    """Is the top window at `point` (physical px) the Astrill window or its child?"""
    at = user32.WindowFromPoint(wintypes.POINT(point[0], point[1]))
    if not at:
        return False
    root = user32.GetAncestor(at, GA_ROOT)
    return root in (hwnd, at) or root == hwnd


def click(x, y, hold=0.08):
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(hold)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


# ---------------------------------------------------------------------------
# status (route table based - no UI needed)
# ---------------------------------------------------------------------------
def vpn_connected():
    """True if the Astrill tunnel (gateway 198.18.0.1 / Wintun) owns the default route."""
    try:
        out = subprocess.run(["route", "print", "-4"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return False
    # Astrill uses the 198.18.0.0/15 range for its tunnel and adds 0.0.0.0/1+128.0.0.0/1
    # routes via 198.18.x.x when connected.
    for line in out.splitlines():
        if re.search(r"\b198\.18\.\d{1,3}\.\d{1,3}\b", line):
            return True
    return False


def public_ip():
    """Best-effort public IP via a few endpoints (may fail behind GFW)."""
    import urllib.request
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://ipv4.icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                ip = r.read().decode().strip()
                if ip:
                    return ip
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------
def do_start(json_out):
    """Launch the Astrill desktop client if it is not already running."""
    if find_astrill_pids():
        if json_out:
            import json
            print(json.dumps({"started": False, "already_running": True}))
        else:
            print("Astrill 已经在运行")
        return 0

    if not ensure_astrill_running():
        print("未找到 astrill.exe,无法启动。请先手动安装/打开 Astrill。")
        return 2

    # wait a few seconds for the main window to appear (client startup takes time)
    hwnd = None
    for _ in range(20):
        hwnd = find_astrill_window()
        if hwnd:
            break
        time.sleep(0.5)
    if json_out:
        import json
        print(json.dumps({"started": True, "window_found": hwnd is not None}))
    else:
        print("Astrill 已启动")
        if hwnd:
            print("主窗口已就绪")
        else:
            print("主窗口尚未出现(客户端可能还在初始化,稍后可用 status 查询)")
    return 0


def get_button_point(hwnd):
    """Return (click_x, click_y, button_state) for the ON/OFF button, or
    (None, None, None) if it cannot be found.
    button_state: 'off' when the orange connect button is visible, else None.
    Strategy: orange colour blob -> relative position fallback."""
    rect = win_rect(hwnd)
    x, y, x2, y2 = rect
    w, h = x2 - x, y2 - y
    if w < 50 or h < 50:
        return None, None, None
    px = capture_rect(x, y, w, h)
    blob = largest_orange_blob(px)
    if blob:
        return x + blob[0], y + blob[1], "off"
    # fallback: the button is roughly at 50% width / 30% height of the window
    return int(x + w * FALLBACK_BTN[0]), int(y + h * FALLBACK_BTN[1]), None


def activate_and_click(hwnd, target):
    """Bring the window forward (safe: click title bar left of the caption buttons)
    and click the target point.  Verifies nothing else covers the target."""
    show_window(hwnd)
    time.sleep(0.3)
    # focus by clicking the title bar (avoid top-right caption buttons & left menu)
    rect = win_rect(hwnd)
    title_x = rect[0] + int((rect[2] - rect[0]) * 0.35)
    title_y = rect[1] + 14
    click(title_x, title_y)
    time.sleep(0.4)

    if not window_belongs_to(hwnd, target):
        return False, "目标点被其他窗口遮挡,无法点击(请把 Astrill 窗口放到前台)"
    click(target[0], target[1])
    return True, None


def wait_for_state(want_connected, timeout=CONNECT_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        if vpn_connected() == want_connected:
            return True
        time.sleep(POLL_INTERVAL)
    return vpn_connected() == want_connected


def do_toggle(want_connected, json_out):
    """Click the button until the VPN reaches the wanted state."""
    if not set_dpi_aware():
        print("无法设置 DPI 感知,坐标可能不准")
        return 2
    if not ensure_astrill_running():
        print("未找到 astrill.exe,且无法启动。请先手动打开 Astrill。")
        return 2
    hwnd = find_astrill_window()
    if not hwnd:
        print("未找到 Astrill 主窗口(可能在启动中)。请稍后重试。")
        return 2

    if vpn_connected() == want_connected:
        state = "已连接" if want_connected else "已断开"
        print(f"无需操作:VPN 已经是{state}状态")
        return 0

    tx, ty, btn_state = get_button_point(hwnd)
    if tx is None:
        print("无法定位连接按钮")
        return 2
    target = (tx, ty)

    clicked_ok, err = activate_and_click(hwnd, target)
    if not clicked_ok:
        print(err)
        return 2

    if not wait_for_state(want_connected):
        state = "已连接" if want_connected else "已断开"
        print(f"等待超时:VPN 未达到{state}状态,请检查 Astrill 窗口")
        return 1

    state = "已连接" if want_connected else "已断开"
    ip = public_ip() if want_connected else None
    if json_out:
        import json
        print(json.dumps({"connected": want_connected, "public_ip": ip}))
    else:
        print(f"VPN {state}")
        if ip:
            print(f"公网 IP: {ip}")
    return 0


def do_status(json_out):
    connected = vpn_connected()
    if json_out:
        import json
        print(json.dumps({"connected": connected, "public_ip": public_ip()}))
    else:
        print("VPN 已连接" if connected else "VPN 未连接")
        ip = public_ip()
        if ip:
            print(f"公网 IP: {ip}")
    return 0 if connected else 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # force UTF-8 output so the CLI works in any modern terminal
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(prog="astrill-cli", description="控制 Astrill VPN(Windows)")
    ap.add_argument("command", choices=["start", "status", "connect", "disconnect"])
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    if args.command == "start":
        return do_start(args.json)
    elif args.command == "status":
        return do_status(args.json)
    elif args.command == "connect":
        return do_toggle(True, args.json)
    elif args.command == "disconnect":
        return do_toggle(False, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
