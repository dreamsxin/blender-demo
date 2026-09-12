# 水晶幻想中式宝剑 (crystal jian)

程序化生成的幻想风中式宝剑：菱形截面的水晶剑身、内部一层冷光剑芯、云纹金属剑格与剑首、
缠绳剑柄配红色剑穗，四周漂浮几块碎晶。暗调棚拍布光 + Cycles 出图。

几何体全部由脚本用基础体和 bmesh 生成，没有外部模型和贴图。

## 跑

```powershell
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup `
  --python "D:\work\blender\demos\props\crystal-sword\scripts\build_sword.py" -- `
  --engine cycles --samples 160 --res 1080
```

- `--engine cycles|eevee`：水晶靠折射吃光，成品图必须 cycles；eevee 只适合看构图
- `--samples` / `--res` / `--out`：采样数、横向分辨率（输出 3:4）、输出路径
- 跑完把场景存成 `crystal_sword.blend`

## 结构 / 参数

脚本顶部常量（Blender 单位，剑竖直朝 +Z，正面朝 −Y，剑格在 z=0）：

- `BLADE_LEN = 0.95`、`BLADE_HALF_W = 0.048`、`BLADE_HALF_T = 0.012` — 剑身长度与菱形截面
- `GRIP_LEN = 0.24`、`TASSEL_LEN = 0.26`、`SHARD_COUNT = 7`
- `blade_profile(t)` — 剑身收窄曲线：前 88% 缓收，最后 12% 收成剑尖；厚度线性减半

## 实现要点

- **剑身**：`build_blade()` 直接用 bmesh 造点造面 —— 每一站一个菱形四点截面，站间连四个四边形，
  末端收成一点，根部封口。**平面着色**（不 smooth）才有水晶棱面该有的硬转折。
- **内部冷光**：同一个函数按 `scale_xy=0.58` 再生成一根缩小的剑芯，材质带自发光，
  外层 `transmission=1.0` 的水晶把它折射出来，就是"晶体内部有光"的效果。
- **符文光带**：三条极薄的发光条按 `blade_profile` 算出的局部宽度贴在剑身上，正面看是三道横向光纹。
- **中式细节**：剑格是一块云头板 + 两侧上翘的角 + 水晶珠；剑柄是漆芯 + 9 圈缠绳；
  剑首云头盘 + 环 + 珠；剑穗用 16 根锥形丝线加一个结，位置由固定随机种子生成（可复现）。
- **布光**：暗背景 + 冷色左后主光 / 右后轮廓光 + 极弱正面补光 + 顶光，另一盏暖光打金属，
  灯全部 `visible_camera = False`；AgX 色彩变换压住发光高光。

## 已知可调项

- 碎晶目前是对顶四棱锥，形状偏规整；想更碎可以随机缩放三个轴或叠几个不同大小的
- 剑穗只做了直线丝线，没有物理垂感；要飘感得上布料模拟或手动弯曲
- 没有做剑鞘
