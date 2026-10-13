# 本地字体

界面使用 Space Grotesk 的拉丁字符和 Noto Sans SC 的中文字符，均以 WOFF2 随项目提供，页面不依赖在线字体服务。两种字体的 SIL Open Font License 1.1 原文保存在本目录。

来源：[Space Grotesk](https://github.com/google/fonts/tree/main/ofl/spacegrotesk)、[Noto Sans SC](https://github.com/google/fonts/tree/main/ofl/notosanssc)。字体保留可变字重，中文文件包含当前界面和演示文本使用的字符；其他输入字符由系统中文字体补齐。

需要重新生成时，在包含 fonttools 和 brotli 的开发环境中执行：

```text
python project/tools/build_fonts.py --space-grotesk path/to/SpaceGrotesk.ttf --noto-sans-sc path/to/NotoSansSC.ttf
```

生成器保留字体的版权及名称信息，只缩减字符集合。正常启动应用不需要安装这两个字体处理工具。
