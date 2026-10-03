# AI 对话背景显示调整记录（2026-08-27）

## 目标



## 实现



## 踩坑与约束

- `message-bubble` 是整行布局容器，对它设置背景会形成横跨消息区的大色块；卡片样式必须落在 `message-surface`。
- 仅写透明 QSS 不足以保证壁纸显示，`QScrollArea` 及其 viewport 的 `autoFillBackground` 仍可能绘制不透明调色板背景。
- 图片缩放语义集中在公共函数，避免经典与现代窗口对 cover/contain/stretch 出现不一致。

## 验证

- 单元测试覆盖两套配置独立保存、渐进显示设置行、消息卡片样式和三种缩放结果。
- 完整测试：196 passed，2 skipped。
- 四个 macOS 应用已重新构建并通过 `codesign --verify --deep --strict`。
