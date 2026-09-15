# 清明上河图 低多边形长卷动画

程序化生成的宋代汴河市井：中间一座虹桥，河上货船，两岸木构屋舍、酒楼、摊铺、垂柳和
赶集的人群。镜头像展开长卷一样沿河匀速横移，低多边形彩色风格，EEVEE 出片。

不是原作的临摹，而是取其"横卷 + 虹桥 + 河市"的结构做的三维演绎；全部几何体由脚本生成
（约 490 个物体），没有外部模型和贴图。

## 跑

```powershell
# 3 秒 720p 预览（默认）
& "D:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup `
  --python "D:\work\blender\demos\scene\qingming-scroll\scripts\build_scroll.py" -- `
  --seconds 3 --fps 24 --res 1280 --samples 32

# 只出一张海报图，用来调构图（最快）
... build_scroll.py -- --still-only --res 960 --samples 16

# 加长到 12 秒 1080p
... build_scroll.py -- --seconds 12 --res 1920 --samples 48
```

- 输出：`render/qingming_scroll_<秒>s.mp4`（H.264）+ `render/qingming_poster.png`（中间帧海报）
- 跑完存 `qingming_scroll.blend`
- `--engine cycles` 可切到 Cycles，但动画逐帧成本高，预览请用默认的 EEVEE

## 结构 / 参数

脚本顶部常量：

- `RIVER_HALF / BANK_H` — 河道半宽、岸高（整条河沿 X 轴铺开）
- `SCROLL_FROM / SCROLL_TO` — 镜头横移的起止 x，决定"卷"展开多长
- `--seconds` 控制时长，船的漂移速度按秒数等比缩放，快慢一致

## 实现要点

- **虹桥**：把桥面拆成 14 段，每段沿 `z = BANK_H + rise·sin(πt)` 的正弦拱线摆放并按切线角旋转，
  栏杆与桥下叠梁同一套参数复用，桥上顺带撒了 7 个行人。
- **屋舍**：`house()` 白墙 + 木柱 + `wedge()` 做的三角棱柱悬山顶，随机瓦顶/茅顶、
  可选二层（阳台 + 栏杆 + 二重檐）、可选临街幌子和自发光灯笼。
- **货船**：平底船身 + 两端用 `wedge` 旋转 90° 拼出的翘头翘尾 + 三段拱形船篷 + 桅帆，
  船工位置随船一起算进人群列表。
- **人群**：先把桥上、船上、摊前、街上的坐标收集成一个列表，最后统一用
  「圆柱身体 + 二十面体头 + 三分之一戴斗笠」批量生成，共 50 人。
- **展卷镜头**：相机朝向固定不变，只给 x 打两个关键帧（起点/终点），
  所以画面是纯粹的横向平移，和看长卷的体验一致。
- **匀速**：Blender 5.x 的 `Action` 已经没有 `fcurves` 属性可以后处理插值，
  改成渲染前设 `preferences.edit.keyframe_new_interpolation_type = "LINEAR"`，
  新插的关键帧直接就是线性的。

## 已知可调项

- 人和船目前是刚体位移，没有走路/摇桨动作；要动起来得给腿部做骨骼或用 shape key
- 水面是平板，没有波纹和倒影；可以加 Wave 修改器或法线贴图
- 屋舍屋顶是三角棱柱，不是真正的歇山/庑殿举折
- 想更像原作可以把镜头压低、加雾、把色板换成绢本淡彩（改 `palette()` 一处即可）
