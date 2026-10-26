# Desktop-Pet

Windows 桌面白龙助手，使用 Python 和 PySide6 实现。项目按角色源码与共享组件分目录管理，目前可运行的角色为 Codex 白龙。

## 目录

```text
desktop-pet/
├── .github/            # GitHub 检查与问题模板
├── Codex/              # 白龙桌宠的应用、角色素材、工具和测试
│   ├── app/
│   ├── assets/character/
│   ├── docs/
│   ├── tests/
│   ├── tools/
│   └── requirements.txt
├── Claude/             # 本地保留的空目录，无模型、素材或程序
├── shared/             # 当前仅由 Codex 调用的共享实现
└── LICENSE
```

Git 不保存空目录，因此仓库检出后不会自动生成 `Claude/`；本机该目录保持完全为空，不放占位文件。

## 运行

使用 Windows x64 和 Python 3.13，从仓库根目录进入 `Codex/`：

```powershell
cd Codex
python -m pip install -r requirements.txt
python app/enhanced.py
```

仓库保留 Codex 白龙的角色动画、会话状态、额度、Token 图表、日报及桌面交互。账户联动需要本机安装并登录 Codex。源码运行和打包都需要保留同级 `shared/`，请下载或备份整个仓库。

## 检查与构建

从 `Codex/` 执行：

```powershell
python tools/check.py
python tools/import_assets.py --check
python tools/build.py
```

构建需要通过校验的高清素材；详细条件和运行方法见 [Codex 使用说明](Codex/README.md)、[开发指南](Codex/docs/DEVELOPMENT.md)及[共享模块说明](shared/README.md)。

源码、文档与角色动画沿用 [CC BY-NC 4.0](LICENSE)，第三方依赖、字体及其许可证按原有条件使用。
