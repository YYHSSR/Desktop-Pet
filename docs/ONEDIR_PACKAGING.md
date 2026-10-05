# 鲸鱼娘便携版打包（2026-10-04）

当前默认交付Windows WebM版。webm-chat是历史构建标识，用于保持现有配置目录和自启项兼容；应用不含内置模型聊天或音效。

## 生成便携目录

在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_onedir.ps1 -Variant webm-chat
```

指定Python时加`-PythonExe <python.exe绝对路径>`。原生编译需MSYS2 UCRT64工具链；脚本先构建、运行CTest并分发pet_core.dll及依赖，再由PyInstaller生成：

`dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe`

整个目录一起复制。只复制exe或删除_internal会丢失Qt、视频和原生依赖。配置默认在APPDATA下，应用图标与角色资源分别随包附带。

## 资源与验收

- 打包assets/characters整套WebM动画与manifest、assets/big_blue_fat_fish自言自语图片、assets/icon.ico、persona_presets及固定menu_templates。
- 分发LICENSE、THIRD_PARTY_NOTICES.md、玩家使用说明README.md和原生依赖；说明和许可证与exe同目录，不包含声音模块或声音文件。
- 构建脚本进行Qt运行库校验、目录精简、中文编码检查、DLL依赖链与原生ABI检查，启动桌宠窗口和独立设置窗口做冒烟验证。
- -SkipBuild针对已有目录重复执行产物校验；需要重编源码时不使用此项。
- 压缩交付前检查ZIP CRC，并记录exe与ZIP的SHA256。原始日志保存在仓库外。

构建目录、spec、dist目录由脚本重新生成且已被.gitignore忽略。图标、角色素材和原生分发库是运行资源，应保留。成品README来自packaging/README.portable.md；根README和docs提供源码使用、开发说明，不直接复制进包。根许可证保留用于源码分发，打包时另复制到成品目录。

## 稳定文件与可选安装包

不要覆盖[冻结的onefile产物](STABLE_BUILDS.md)。当前构建目录独立于dist中的稳定文件。

需要安装包时使用Inno Setup编译packaging/dsh-pet-webm-chat.iss；构建便携目录不代表已生成或验证安装包。

相关入口：[README](../README.md)、[开发交接](DEV-HANDOVER.md)、[文档索引](INDEX.md)。
