# astrill-cli-skill

在 Windows 上自动控制 [Astrill VPN](https://www.astrill.com/) 桌面客户端(3.x)的 CLI + pi 技能。

Astrill 没有官方的 Windows CLI,内部协议(ASProxy 服务,端口 12344)也是专有的,所以本工具采用 **UI 自动化**方式驱动已登录的桌面客户端:

- 通过进程名(`astrill.exe`)动态查找主窗口(PID、窗口位置变化都不影响)
- 截图窗口,用**颜色检测**定位橙色的 ON/OFF 连接按钮(断开时为橙色,连接后变灰)
- 点击按钮切换连接;`status` 直接读 Windows 路由表判断隧道状态(不依赖 UI)

## 要求

- Windows 10+、Python 3.8+(仅标准库,零第三方依赖)
- Astrill 桌面客户端已安装、已登录(本工具不会处理登录/订阅)

## 安装

```bash
# 无需 pip 安装任何东西。可选的:做个别名/复制到 PATH
alias astrill='python D:/astrill-cli-skill/astrill_cli.py'
```

## 用法

```bash
python astrill_cli.py start         # 启动客户端(未运行才启动,已运行直接跳过)
python astrill_cli.py status        # VPN 是否已连接(含公网 IP)
python astrill_cli.py connect       # 连接 VPN(点击按钮并等待隧道建立)
python astrill_cli.py disconnect    # 断开 VPN
python astrill_cli.py status --json # 机器可读输出
```

退出码:`0` = 成功 / 已连接;`1` = 状态为未连接 / 操作超时;`2` = 环境错误(找不到窗口等)。

示例:

```bash
$ python astrill_cli.py status
VPN 未连接
公网 IP: 114.86.5.188

$ python astrill_cli.py connect
VPN 已连接
公网 IP: 104.168.14.206
```

## 工作原理

| 命令 | 机制 |
|---|---|
| `start` | 通过 `tasklist` 检查 `astrill.exe`;未运行则从注册表 `HKLM\SOFTWARE\Astrill` 或常见安装路径找到 exe 并启动,然后轮询等待主窗口出现(幂等,已运行直接返回) |
| `status` | 解析 `route print -4`:存在 `198.18.x.x` 网关(默认路由 0.0.0.0/1 + 128.0.0.0/1 经 Wintun 隧道)= 已连接 |
| `connect` / `disconnect` | ① 未运行时自动 `start` → ② 按进程名找 Astrill 主窗口 → ③ 置前、截图 → ④ 在上部 55% 区域找橙色按钮(找不到则按窗口相对位置 fallback)→ ⑤ 点击 → ⑥ 轮询路由表直到状态切换 |

注意点(踩过的坑):

- 进程必须 **DPI-aware**(`SetProcessDpiAwarenessContext`),否则屏幕坐标会被系统按缩放比例钳制,点击全部落空
- 点击前用 `WindowFromPoint` 校验按钮位置没有被其他窗口遮挡
- 激活窗口时点击标题栏中部偏左,避开右上角关闭按钮和左上角菜单
- 连接后按钮变灰,因此断开时用相对位置 fallback(按钮中心约在窗口宽 50%、高 30% 处)

## pi 技能

`skill/SKILL.md` 是 [pi](https://github.com/earendil-works/pi-coding-agent) 的技能定义。把 `skill/` 目录链接/复制到技能目录(如 `~/.pi/agent/skills/astrill/`)即可让 pi 直接使用:

```bash
mkdir -p ~/.pi/agent/skills
cp -r skill ~/.pi/agent/skills/astrill
```

之后 pi 里执行 `connect`、`disconnect`、`status` 即可控制 VPN。

## 目录

```
astrill_cli.py      # CLI(单文件,零依赖)
skill/SKILL.md      # pi 技能定义
README.md
```

## 局限

- 依赖 GUI:需要桌面会话、Astrill 窗口不被完全遮挡;纯 headless(无桌面)环境不可用
- 只支持 Windows(Astrill 客户端平台限制)
- 服务器切换暂未实现(Astrill v3.10 窗口的服务器栏/协议选择器点击无响应,待研究)
