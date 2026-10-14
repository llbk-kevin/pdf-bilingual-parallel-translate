# 状态驱动的构建

把 scripts/example_build.py 和 scripts/workflow.py 复制到任务输入状态旁，在合适环境安装 requirements-dev.txt。明确传入 --source、--state 和 --output。范例只读输入状态，输出 PDF、<output>.state.json 及 <output>.font-runs.json；输出状态包含实际绘制边界且 qc 已清空。审计和渲染使用该输出状态，不使用带旧边界的输入状态。

## 工作文件与发布

输入状态和构建器放在 <source-stem>/recovery/，候选 PDF、构建伴随文件、提取、渲染及审计报告放在 <source-stem>/work/。构建始终在工作文件夹内进行，因为范例会在 PDF 旁生成伴随文件；不要直接构建到外层交付路径。交付说明.md 保留在 <source-stem>/ 内。

冻结的候选版本通过翻译、视觉和结构验收后：

1. 检查外层 <source-stem>_双语左右对照翻译.pdf 目标与原文及已有文件不冲突。只复制已验收 PDF，保持字节不变，并验证 SHA-256 与冻结候选一致。未解决的草稿仍放在 work/ 内。
2. 当前状态放在 recovery/，辅助报告和证据留在同一工作文件夹内。尽量在审阅前确定位置；需要迁移当前状态时，先按旧基准目录解析每个相对引用，再按新基准目录重写相对路径。仅修改迁移所需路径，保留语义数据和数值类型；涉及指纹中的路径时，遵循状态与审核参考的迁移规则。不改写历史快照或不可改写的渲染索引。
3. 将当前 output.path 指向外层 PDF，优先使用相对于状态文件的路径。由于 PDF 字节未变，输出哈希和 qc 保持原样。针对发布后的 PDF 及保留证据，对当前状态运行 check-state --final；发布路径和相同哈希记录在工作文件夹内。不把复制或更新 output.path 冒充新审阅。

已验收 PDF 必须嵌入独立阅读、渲染、搜索和复制所需的字体及资源。恢复文件用于编辑和验证，不是 PDF 的运行依赖。验证交付目录时，使用可丢弃的副本，只移除经过路径核验的副本工作文件夹，并确认两个 PDF 仍可渲染、提取文字且结果不变。不自动删除用户的工作文件夹。

## 布局与恢复

每块需要输出左上坐标的 target_bbox、完整 translation 及 status；表格读取 table.translated_rows，可有 col_proportions 和 spans [x0,y0,x1,y1]，并提供同形 source_rows。reading_order 列出块 ID。字体记录 name、source 路径、sha256、purpose，可有 face_index；block.font 指定首选字体。构建器逐缺字选择已验证的备用字体并记录实际使用者及 fallback_from，不能以字体集合的覆盖代替选中字体覆盖。格式不支持时明确未验证或失败。

范例支持未旋转、未裁切、零原点页面上的段落、sub/sup 标记及真实表格。遇到 pending 块、无效映射、覆盖原文、缺字和溢出就停止。通过全书单一 overlay 共享字体，由 ReportLab 子集化，压缩内容流并清理废弃对象。复杂数学、图形布局、旋转/裁切标准化及重叠设计由任务构建器处理，输出必须查看。

中文区始终匹配每页原文，输出为 2W × H。已有 layout.pane_width_pt 仅在与该页源宽相差不超过 0.1 pt 时接受，不能用于加宽；混合页宽应省略该字段。范例使用明确的 block.font_size 和 leading，不自动缩字或重排；查看可用空间后，在输入状态调整 target_bbox/font_size，再重新构建。

可选的显式页码使用 layout.pagination_strategy 和逐页 pagination，见 [state-and-qc.zh-CN.md](state-and-qc.zh-CN.md)。范例在 target_bbox 内右对齐绘制已确认文字，并纳入实际字体片段。不识别原页码，也不自动选择位置。原页码文字归入此记录，不再同时作为正文/页脚翻译块；新增页码是版面补充，不伪造原文文字。

执行 check-fonts OUTPUT.state.json --assignments OUTPUT.font-runs.json --out fonts.json。自定义构建器输出同样结构：schema_version:1、output_sha256，以及包含 page、block、font、text、可选 fallback_from 的 runs。片段须来自实际绘制，按顺序覆盖每块渲染文字和完整表格单元格，字体名称对应登记表。声明片段覆盖通过不证明 PDF 嵌入或字形显示正确。

恢复验证时将状态、构建器及辅助模块复制到独立目录，标明外部原文和字体依赖并在那里重建。修改副本中一个实际存在的译文块；有表格时再修改一个单元格，确认提取/渲染结果变化且输入没有被重置。纯文字文档无需为此检查新增表格。不改数据重复构建两次，对比字节/资源，不能累积资源。恢复说明记录依赖和命令，不为了测试而修改已验收包。

构建器保留并核对已声明的 layout.inputs，输出状态记录实际 Python、pypdf 和 ReportLab 版本。跨环境重建若字节不同，核对绘制指令、文字、资源及渲染结果，并记录具体原因；重复运行仍应稳定，不能仅因视觉相同就忽略不明差异。
