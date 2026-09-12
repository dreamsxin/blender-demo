# blender-mcp demo 仓库

用 AI 助手驱动 blender-mcp / Blender Python 制作各类 demo（模型导入、渲染、动画控制）的工作仓库。

## 环境

- Windows 10，Blender **5.2.1 LTS**：`D:\Program Files\Blender Foundation\Blender 5.2\blender.exe`
- blender-mcp addon：安装与"偏好设置里搜不到插件"的排查过程见 [blender-mcp-install.md](blender-mcp-install.md)
- mmd_tools 扩展（模块名 `bl_ext.user_default.mmd_tools`）：导入 MMD 的 `.pmx` 模型

## 目录

- `克拉蕾/` — MMD 模型（`克拉蕾.pmx`，926 根骨骼，标准 MMD 骨架 + 足 IK）
  - `render/` — 三视图效果图（front / three_quarter / side）
  - `render/control/` — 行走、跳跃动作的预览帧
- `南宫羽/`、`南宫羽_狂想缪斯/` — 南宫羽 两套服装的 MMD 模型；狂想缪斯已渲三视图并做过动画控制自检
- `咖啡杯&场景/`、`小凳子场景&效果图/`、`萌三兄弟/` — 练习用 blend 源文件与效果图
- `*.zip` — 原始素材包，体积大，未入库（见 `.gitignore`）

## 脚本

两个脚本都是通用的，靠命令行参数指定模型：

| 脚本 | 用途 | 入口 |
| --- | --- | --- |
| `render_pmx.py` | 导入任意 `.pmx`，自动三点布光、构图、曝光校准，输出三视图 | `blender.exe -b --factory-startup --python render_pmx.py -- --model <pmx> [--name <前缀>]` |
| `mmd_control.py` | MMD 角色 行走 / 跳跃控制（键盘实时控制 + 关键帧烘焙），参数按身高自动缩放 | 见 [mmd_control使用说明.md](mmd_control使用说明.md) |

## 会话记忆约定

AI 会话的上下文靠**文档 + git log**恢复，因此：

1. 每完成一件事，先更新对应文档（本 README 的进度 + 专项说明），再提交。
2. commit message 写清「做了什么 + 验证结果」，方便 `git log` 当时间线读。
3. 恢复会话时的阅读顺序：`README.md` → `git log --stat` → 专项说明文档。
4. 会话原文备份在 `D:\work\sessions\chat_session_<uuid>`（JSON，不在本仓库内）。

## 进度

- **2026-09-11**
  - 装好 blender-mcp addon（踩坑：装到了 3.5 配置目录，实际用的是 5.2），过程记录成文档。
  - 解压 `克拉蕾.zip`，用 mmd_tools 导入 PMX，渲出三视图效果图。
  - 写好 `克拉蕾_control.py`：行走 / 跳跃控制，无界面自检通过（脚不打滑、跳跃抛物线正常），并渲出预览帧。
- **2026-09-12**
  - 脚本改成通用：`_render_claret.py` → `render_pmx.py`（`--model/--out/--name/--scale`），
    `克拉蕾_control.py` → `mmd_control.py`（`--model`，动作参数按身高自动缩放，action 改名 `MMD_Walk/MMD_Jump`，面板页签 "MMD 控制"）。
  - 渲出 南宫羽_狂想缪斯 三视图（身高 1.562，31225 顶点），并在该模型上跑通行走/跳跃自检与预览帧；克拉蕾 回归自检同样通过。
