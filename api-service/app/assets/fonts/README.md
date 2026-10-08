# 报告字体资源

上游：<https://github.com/notofonts/noto-cjk>，revision `f8d157532fbfaeda587e826d4cd5b21a49186f7c`。
源文件：`Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf`（简体中文地域字形）。
许可：同 revision `Sans/LICENSE`，随本目录 `OFL.txt` 分发，SIL OFL 1.1。
字体内部保留上游版权信息；仅用于嵌入应用生成的报告，不单独销售。

机械生成（FontTools 4.63.0，构建时使用，运行时无此依赖）：

```
python -m fontTools.varLib.instancer NotoSansSC-VF.ttf wght=400 --update-name-table --output NotoSansSC-Regular.ttf
python -m fontTools.varLib.instancer NotoSansSC-VF.ttf wght=700 --update-name-table --output NotoSansSC-Bold.ttf
```

PDFGenerator 从模块路径加载并按 PDF 内容嵌入子集，不依赖 cwd、系统字体或网络。
Docker 已通过 `COPY app/ ./app/` 包含此目录。
