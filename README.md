# PDF 双语左右对照翻译

## 工作约定

使用当前会话模型翻译，不调用外部机器翻译。先检查当前 PDF 的语言、主题、体裁、读者与版式，再选择术语；不能从之前的任务推断领域。保留含义、不确定性、条件和限定，不擅自纠正疑似原文错误。

文本使用 UTF-8 无 BOM。普通使用只读英文入口和相关英文参考。明确维护技能时，同步中文 README 及成对参考文件，遵循 AGENTS.md 与 [maintenance.zh-CN.md](references/maintenance.zh-CN.md)。保留 CC Switch 链接，修改解析后的本体；文档任务产物和字体二进制放在仓库之外。

每份文档阅读 [naming.zh-CN.md](references/naming.zh-CN.md)。根据内容识别原文/译文角色，不根据文件名判断。原文改名前提出准确的新旧名称对照表，确认后执行；已接受的 Plan 已批准该表时无需再次确认。保留原文和已有输出。原文文件名使用已确认的编号（如有）、真实原语言标题和中文标题；只有生成译文带翻译后缀。仅确认属于 TI 的文档使用 TI 专属规则。

默认路径如下，用户指定位置优先：

~~~text
<source-directory>/
|-- <source-stem>.pdf
|-- <source-stem>_双语左右对照翻译.pdf    # 仅已验收 PDF
+-- <source-stem>/
    |-- 交付说明.md
    |-- recovery/                  # 状态、构建器、术语及再生成说明
    +-- work/                      # 草稿、提取、渲染和审阅证据
~~~

候选版本构建在 work/，只发布已验收 PDF，伴随文件留在同名工作文件夹内。PDF 应嵌入独立阅读、渲染、搜索和复制所需的全部资源。不自动删除工作文件夹；交付时说明删除它会丢失保存的编辑状态、证据及继续/再生成能力。

## 必须达到的结果

每个可见原页 W × H 严格对应一个 2W × H 合成页：左侧原文保持 1:1，右侧中文页等宽等高，逐页处理混合尺寸、裁切和旋转。右侧复用原页完整图形、照片、曲线、表格线和公式，仅在原位置替换需要翻译的原生文字；无需翻译的数值、标识及数学符号保留。图片或转曲标签可使用明确边界的白底覆盖和黑色中文。

译文保持靠近原文；可使用已核实的相邻空白和适度的逐块字号拟合，并记录允许范围及实际结果。不移动图框/表格框、不扩大页面、不截断、不遗漏限定、不悄悄切回旧版纯文字右侧布局。完整内容仍无法清晰放下时，保留草稿，指出具体块和可选取舍。

## 默认流程

1. **检查与提取。** 执行接口见 [inplace.zh-CN.md](references/inplace.zh-CN.md)。检查原文，保留 SHA-256 和资源基线，渲染代表页；运行 extract 创建 v3 状态。对照可见原页检查图片/转曲文字、隐藏 OCR、分栏、公式和印刷页码。语义分组与拟合遵循 [layout.zh-CN.md](references/layout.zh-CN.md)。
2. **翻译与映射。** 使用 extract 的稳定 ID 并核对 source_text，不使用另一轮抽取的块序号直接贴译文。合并/拆分块时保留字形 ID 及完整覆盖。指定 replace、cover、preserve（含理由）或 unresolved。按连贯段落翻译，维护精简术语表，记录原文疑点、准确原句和处理方式；不需翻译的公式和数值保留。有数学记号时使用 [math.zh-CN.md](references/math.zh-CN.md)。每批完成后保存输入状态。
3. **构建并查看样页。** 登记许可字体及指纹。默认原位构建器从原文和状态生成，不叠加旧双语 PDF。它共享原图资源，仅删除选中的原生文字，绘制中文并记录实际字体 runs，最后在全文件范围子集化。不支持的交互/文字剪裁特性及溢出明确失败。批量处理前检查密集表格、彩底、公式邻近文字、封面和旋转页面。保真限制见 [pdf-integrity.zh-CN.md](references/pdf-integrity.zh-CN.md)。
4. **验证冻结候选。** 使用生成的状态执行 check-state、check-fonts、audit 和 render。实际查看每页，并翻译/核对所有清点块；仅渲染不算审阅。用具体证据处理警告；按 [state-and-qc.zh-CN.md](references/state-and-qc.zh-CN.md) 保存与页面绑定的审阅记录、失效关系及 --final 验证。修改后重新构建并复核受影响上下文。程序成功不证明语义正确。
5. **交付与恢复。** 验证由状态独立重建后，按 [building.zh-CN.md](references/building.zh-CN.md) 发布已验收 PDF。报告原文/输出位置与字节体积、绝对及百分比增量、图片/字体/内容流增量、页数覆盖、审阅状态和保留疑点。局部试样不得称为完成的整份译文。

## 命令

发现可用的 Python 3.10+ 并安装 requirements.txt；开发测试和旧范例另需 requirements-dev.txt。优先使用已有合适环境或独立环境。不将本机运行时绝对路径写入技能，也不为绕过 shell 故障而污染共享 Python。

~~~text
python scripts/inplace.py extract --source SOURCE --state recovery/state.json --pages all
python scripts/inplace.py build --source SOURCE --state recovery/state.json --output work/draft.pdf --pages all
python scripts/pdf_tools.py inspect SOURCE --out work/baseline.json
python scripts/pdf_tools.py check-state work/draft.state.json --out work/state-check.json
python scripts/pdf_tools.py check-fonts work/draft.state.json --assignments work/draft.font-runs.json --out work/fonts.json
python scripts/pdf_tools.py audit SOURCE work/draft.pdf --state work/draft.state.json --out work/audit.json
python scripts/pdf_tools.py render work/draft.pdf --source SOURCE --state work/draft.state.json --pages all --out work/renders
~~~

以上路径在文档工作文件夹内解析，含空格路径加引号。--pages 接受 all 或从 1 开始的 1,3-5 等选择；局部构建只作为试样，不能通过完整交付的覆盖检查。覆盖已有目标须显式 --overwrite。空用户密码 PDF 可直接打开，其他密码仅从用户提供的 --password-env 环境变量取得，不记录到状态或日志。

诊断默认采用 144 DPI、4000 万像素、RGB 容差 16 和变化比例 0.001。调查差异，不放宽阈值掩盖问题。退出码：0 为程序完成（可能仍有警告），2 为诊断检查失败，1 为操作失败。quality_certified 始终为 false。v1/v2 状态保留原有审阅语义并继续可读；scripts/example_build.py 仅供明确选择的兼容路径，不自动回退。
