# Ya Ya 泡罩包装 (90s blister pack)

程序化生成的 90 年代动作人物泡罩包装：左边一个 Q 版 3D 打印风人物，右边 6 个配件泡罩，
卡纸底板印卡通篮球场，标题 "Ya Ya"，右上角小字 "Designed by yaya"。

全部几何体都是脚本里用基础体 + bmesh 倒角生成的，没有外部模型或贴图文件；底板印刷图案由
numpy 现算成 1400×1946 的贴图。

## 跑

```powershell
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup `
  --python "D:\work\blender\demos\product\toy-blister\scripts\build_blister.py" -- `
  --engine cycles --samples 160 --res 1080
```

- `--engine cycles|eevee`：EEVEE 出图快但透明泡罩会发灰，成品图用 cycles
- `--samples`：Cycles 采样数（预览 24 够看构图）
- `--res`：横向分辨率，输出固定 3:4
- `--out`：输出 png 路径，默认 `render/yaya_blister.png`

跑完同时把场景存成 `yaya_blister.blend`，可以在 GUI 里继续调。

## 版式 / 参数

脚本顶部常量（Blender 单位，卡片立在 XZ 平面，泡罩朝 −Y 即镜头方向）：

- `CARD_W/CARD_H = 2.30 / 3.20`，`CARD_T` 卡纸厚度
- `FIG_BUBBLE / FIG_CENTER`：人物泡罩尺寸与位置；`FIG_HEIGHT = 1.80`，头身比 1:2.5
- `ACC_COLS / ACC_ROWS / ACC_BUBBLE`：右侧 2 列 × 3 行配件泡罩
- `LOGO_Z / CREDIT_Z / HANG_Z`：标题、右上角小字、挂孔高度
- 配件顺序：篮球 / 球鞋 / 小书包 / 水壶 / 发夹 / 跳绳

## 实现要点

- **泡罩**：`rounded_box(open_back=True, thickness=...)` —— 倒角立方体删掉朝 +Y 的背面再
  solidify，就是一个真空吸塑的壳；外圈另加一片薄法兰。倒角面用平滑着色、平面保持硬边，
  塑料的转折才干净。
- **人物**：球 + 锥台 + 圆环拼的，材质带 Wave 贴图做微弱层纹 bump，模拟 3D 打印质感。
  头发用"球心往后挪"的办法遮住后脑而不糊脸：前半球落在皮肤球里面自然被遮掉。
- **底板印刷**：numpy 直接按掩码画色带、球场边线、中圈、罚球区、三分弧、篮筐与篮板，
  再叠一层半调网点和纸张噪声；挂孔也是画上去的（正面平拍看不出差别）。
- **文字**：3D 文字曲线（默认字体 + `offset` 伪加粗），比贴图里画字更清晰。

## 说明

- 人物造型参考了照片里的元素（双马尾 + 小发夹、玫红外套、绿格子裙、黄鞋），**不做人脸还原**，
  走潮玩 Q 版路线。
- 出的是三维渲染质感，不是"实拍照片"质感；要照片感需要后期或换用图像生成模型。
