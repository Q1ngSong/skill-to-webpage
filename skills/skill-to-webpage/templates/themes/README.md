# 主题目录

页面布局与交互完全不变,只通过 CSS 变量换肤。机制与 book-to-webpage 相同:

- `docs.css` 的变量块就是 `base.html` 里 `:root` 的默认值(**默认主题**);
- 其余 3 个文件各是一个 `[data-theme="X"]` 覆盖块;
- 渲染时 **4 套全部内联**进生成的 HTML `<style>`,不引用外部文件;
- `<body data-theme="...">` 控制当前生效主题,右上角下拉切换,localStorage 记忆(key:`s2w-theme`)。

| 主题 ID | 名称 | 气质 | 适合场景 |
|---|---|---|---|
| `docs`(默认) | 简洁文档 | 白底大留白,Linear/Notion 风,克制的靛蓝强调 | 最百搭,通用默认 |
| `blueprint` | 技术蓝图 | 深蓝底 + 浅蓝描边,工程图纸感 | 强调"可执行规格"的技术读者 |
| `ide` | 终端 IDE | 编辑器暗色调 + 语法高亮配色 | 开发者读者,夜间阅读 |
| `whiteboard` | 白板手绘 | 暖米底 + 大圆角便签卡片 | 讲给非技术人听 |

## 变量契约

每套主题必须完整定义以下变量(组件 CSS 只引用变量、不写死颜色):

```
--bg --surface --surface-2 --ink --ink-soft --muted --line
--accent --on-accent --accent-soft --ok --warn --chip
--code-bg --code-ink --tooltip-bg --tooltip-ink
--radius --shadow --font-body --font-display --font-mono
```

`--tooltip-bg/--tooltip-ink` 单独抽出是为了避免暗色主题下 tooltip/toast 反相不可读(book-to-webpage 的 dark.css 用局部覆盖补丁解决,我们改为变量化,主题文件无需组件补丁)。

新增主题:复制 `docs.css` 改名,包一层 `[data-theme="你的ID"] { ... }`,把全部变量换成新配色,再在 `base.html` 的 `<select id="themePicker">` 加一个 option。
