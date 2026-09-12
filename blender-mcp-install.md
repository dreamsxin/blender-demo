# blender-mcp 安装记录

- 日期：2026-09-11
- 项目：https://github.com/ahujasid/blender-mcp
- 环境：Windows 10 / Blender 5.2.1 LTS（安装于 `D:\Program Files\Blender Foundation\Blender 5.2\`）

## 1. 安装 addon

```powershell
uvx blender-mcp install-addon
```

输出提示装到了：

```
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.5\scripts\addons\blender_mcp.py
```

## 2. 问题：Blender 偏好设置里搜不到插件

原因：安装脚本挑错了配置目录。本机存在三份 Blender 配置：

```
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.0
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.5
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2   <- 实际在用
```

实际运行的是 5.2，而插件被放进 3.5，因此 5.2 扫描不到。

排查方式（确认真实版本与安装路径）：

```powershell
Get-ChildItem "C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender"
Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" |
  Where-Object { $_.DisplayName -match "Blender" } |
  Select-Object DisplayName, DisplayVersion, InstallLocation
```

## 3. 修复：复制到 5.2 的 addons 目录

```powershell
$dst = "C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons"
New-Item -ItemType Directory -Path $dst -Force
Copy-Item "C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.5\scripts\addons\blender_mcp.py" -Destination $dst -Force
```

## 4. 验证加载（无界面模式）

```powershell
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup `
  --python-expr "import addon_utils; m=addon_utils.enable('blender_mcp', default_set=False); print('ENABLE_RESULT:', m)"
```

结果：

```
BlenderMCP: cannot start server in background mode (blender -b) - commands would never execute
BlenderMCP addon registered
ENABLE_RESULT: <module 'blender_mcp' from '...\5.2\scripts\addons\blender_mcp.py'>
Blender 5.2.1 LTS
```

`cannot start server in background mode` 属预期提示，MCP server 必须在有 GUI 的 Blender 中启动。

## 5. 在 Blender 中启用

1. 重启 Blender。
2. Edit → Preferences → Add-ons，搜索 `MCP`；若搜不到，把来源筛选切到 **All** / **User**（分类为 `Interface`，名称 "MCP for Blender"）。
3. 勾选启用。
4. 3D 视图按 `N` 打开侧边栏 → **MCP for Blender** 标签页 → 点击 **Start MCP Server**。

## 备注

- 插件版本 `bl_info version (1, 6)`，最低要求 Blender 3.0.0，`ADDON_PROTOCOL_VERSION = 5`。
- 3.5 目录下的旧副本仍保留，确认 5.2 正常后可删除：
  `C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\3.5\scripts\addons\blender_mcp.py`
- 以后升级 addon 时注意 `uvx blender-mcp install-addon` 可能再次写入 3.5，需重复第 3 步。
