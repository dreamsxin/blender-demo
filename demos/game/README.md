# 游戏 demo

放用 Blender 做的游戏向 demo：可玩原型、实时交互脚本、导出到引擎的资产管线等。当前为空，等第一个 demo 落地。

## 单个 demo 的目录约定

```
demos/game/<demo-slug>/
  README.md      # 这个 demo 做什么、怎么跑、结论与踩过的坑
  *.blend        # 工程文件
  scripts/       # 该 demo 专属脚本（跨 demo 复用的放仓库根 scripts/）
  render/        # 渲染输出、预览帧、录屏截图
  assets/        # 该 demo 专属素材；大文件在 .gitignore 里排掉
```

- 目录名用 ASCII slug（小写 + 连字符），中文名写在该 demo 的 README 标题里。
- 脚本一律支持无界面自检（`blender -b --python ... -- --selftest`），把可断言的结论写进 README。
