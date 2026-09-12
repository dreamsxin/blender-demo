# blender-mcp demo 仓库

用 AI 助手驱动 blender-mcp / Blender Python 制作各类 demo（模型导入、渲染、动画控制）的工作仓库。

## 环境

- Windows 10，Blender **5.2.1 LTS**：`D:\Program Files\Blender Foundation\Blender 5.2\blender.exe`
- blender-mcp addon：安装与"偏好设置里搜不到插件"的排查过程见 [docs/blender-mcp-install.md](docs/blender-mcp-install.md)
- mmd_tools 扩展（模块名 `bl_ext.user_default.mmd_tools`）：导入 MMD 的 `.pmx` 模型

## 目录结构

```
blender-demo/
├─ README.md              # 索引 + 会话记忆（先读这里）
├─ docs/                  # 说明文档
│  ├─ blender-mcp-install.md
│  ├─ mmd-control.md
│  └─ images/             # 教程截图等
├─ scripts/               # 跨 demo 复用的通用脚本
│  ├─ render_pmx.py
│  └─ mmd_control.py
└─ demos/                 # 按类型分的 demo
   ├─ character/          # 角色类：MMD 导入 / 渲染 / 动画控制
   │  ├─ claret/          # 克拉蕾
   │  ├─ nangongyu/       # 南宫羽（默认服装）
   │  └─ nangongyu-muse/  # 南宫羽 狂想缪斯
   ├─ modeling/           # 建模练习
   │  ├─ coffee-cup/      # 咖啡杯 & 场景
   │  ├─ stool/           # 小凳子场景
   │  └─ moe-brothers/    # 萌三兄弟
   ├─ product/            # 产品 / 包装类
   │  └─ toy-blister/     # Ya Ya 90s 泡罩包装 (程序化建模 + Cycles 渲染)
   ├─ props/              # 道具 / 单体资产
   │  └─ crystal-sword/   # 水晶幻想中式宝剑 (程序化建模 + Cycles 渲染)
   └─ game/               # 游戏 demo（预留，约定见 demos/game/README.md）
```

约定：

- **目录名用 ASCII slug**（小写 + 连字符），中文名写在 README 或该 demo 的 README 里；避免中文路径在 PowerShell / 工具链里踩坑。
- 新增一类 demo 就在 `demos/` 下开一个类别目录（如 `demos/rendering/`、`demos/simulation/`），类别内每个 demo 一个 slug 目录。
- 单个 demo 内部：工程文件放根目录，输出统一进 `render/`（动画预览进 `render/control/`），专属脚本进该 demo 的 `scripts/`。
- **脚本和场景都保留**：脚本跑完会把场景存成 `.blend`（`render_pmx.py` → `<name>_render.blend`，
  `mmd_control.py --selftest` → `<name>_control.blend`，toy-blister → `yaya_blister.blend`），
  方便直接打开继续调；`.blend1` 备份不入库。
- 通用脚本放仓库根 `scripts/`，默认路径基于 `repo_root()` 推导，不写死绝对路径。
- 原始素材（`*.zip`、`*.pmx`、`tex/`、`spa/`）不入库，可从素材包重新解出，见 `.gitignore`。

## 脚本

两个脚本都是模型无关的，靠命令行参数指定模型：

| 脚本 | 用途 | 入口 |
| --- | --- | --- |
| `scripts/render_pmx.py` | 导入任意 `.pmx`，自动三点布光、构图、曝光校准，输出三视图 | `blender.exe -b --factory-startup --python scripts/render_pmx.py -- --model <pmx> [--name <前缀>]` |
| `scripts/mmd_control.py` | MMD 角色 行走 / 跳跃控制（键盘实时控制 + 关键帧烘焙），参数按身高自动缩放 | 见 [docs/mmd-control.md](docs/mmd-control.md) |

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
  - 规划并落地目录结构：`docs/` + `scripts/` + `demos/{character,modeling,game}`，目录名统一 ASCII slug；
    脚本默认路径改为按 `repo_root()` 推导；顺手渲出 南宫羽（默认服装）三视图。
  - 新增 `demos/product/toy-blister/`：程序化生成 Ya Ya 90 年代泡罩包装（Q 版人物 + 6 个配件泡罩 +
    卡通篮球场底板 + 标题文字），Cycles 出图，详见该 demo 的 README。
  - 新增 `demos/props/crystal-sword/`：程序化生成水晶幻想中式宝剑（菱形截面剑身 + 内部冷光剑芯 +
    云纹剑格剑首 + 缠绳剑柄 + 红剑穗 + 漂浮碎晶），暗调布光 Cycles 出图。
  - 约定补充：脚本跑完顺手保存 `.blend`，脚本与场景一起入库。
