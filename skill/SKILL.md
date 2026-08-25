---
name: astrill
description: 控制 Windows 上的 Astrill VPN 桌面客户端(启动/连接/断开/状态查询)。当用户需要开 VPN(如访问 GitHub、被墙网站)、关 VPN、检查 VPN 是否连接、或切换网络出口时使用。需要 Astrill 客户端已安装并登录。
---

# Astrill VPN 控制

通过 `astrill_cli.py` 驱动已登录的 Astrill 桌面客户端(GUI 自动化),无需管理员权限。

## 前提

- Windows 10+、Python 3.8+(仅标准库)
- Astrill 客户端已安装、已登录(本技能不处理登录)
- 需要桌面会话(有可见桌面的环境)

## 命令

在技能目录下用相对路径执行(`python` 不可用时用 `py`):

```bash
cd ~/.pi/agent/skills/astrill
python astrill_cli.py start         # 启动客户端(已运行则跳过)
python astrill_cli.py status        # 查询状态
python astrill_cli.py connect       # 连接
python astrill_cli.py disconnect    # 断开
python astrill_cli.py status --json # JSON 输出
```

## 退出码约定

- `0`:成功(start 已启动/已运行;connect/disconnect 完成;status 且已连接)
- `1`:status 且未连接;或操作超时(VPN 状态未在 40s 内切换)
- `2`:环境错误(找不到 astrill.exe/窗口/无法启动/无法定位按钮)

## 使用说明

0. **启动** — 如果 Astrill 客户端未运行,先执行 `start` 启动它(会自动查找注册表/常见安装路径);已运行则直接跳过。
1. **连接** — 如果 `status` 显示未连接,执行 `connect`;若显示已连接则无需操作。
2. **断开** — 同理,已连接才需要 `disconnect`。
3. **失败排查**:
   - 退出码 `2` 且提示找不到 astrill.exe → 确认已安装 Astrill,或手动打开一次
   - 退出码 `2` 且提示找不到窗口 → Astrill 进程在但主窗口未出现,稍后重试 `status`/`connect`
   - 提示"目标点被其他窗口遮挡" → 把 Astrill 窗口移到前台后重试
   - 连接超时 → 可能是服务器网络问题,重试一次或检查 Astrill 界面状态
4. **公网 IP**:`connect`/`status` 输出里的 IP 若为国内 IP(如 114.x/223.x 等)说明未生效,可等待几秒后重查 `status`。

## 使用场景建议

- **GitHub / 被墙网站(必开 VPN)**:访问 GitHub(含 `git clone`、`git push`、下载 release、`gh` CLI)、Google、Stack Overflow 等被墙站点前,必须执行 `connect`。完成后按需 `disconnect`。
- **npm(推荐关 VPN + 国内镜像)**:执行 `npm install` / `npm publish` 等操作时,推荐先 `disconnect` 关闭 VPN,并把 registry 设为国内镜像,否则流量走 VPN 出口会导致下载慢、超时或失败:

  ```bash
  npm config set registry https://registry.npmmirror.com   # 淘宝 npmmirror 镜像
  npm config get registry                                    # 确认生效
  ```

  注意:关闭 VPN 后 npm 可能因代理环境变量(NODE_OPTIONS/HTTP_PROXY 等)仍走代理,如异常可检查 `npm config get proxy` 和 `npm config get https-proxy`。

## 注意

- 不要修改 `astrill_cli.py` 的窗口查找/按钮定位逻辑(按进程名 + 颜色检测,自适应窗口位置)
- 服务器切换功能暂未实现,不要承诺可以切换 Astrill 服务器
- 本技能涉及网络代理,配合其他任务(如访问被墙网站)时,先 connect 再执行目标任务,完成后按需 disconnect
