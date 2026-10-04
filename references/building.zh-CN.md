# 状态驱动的构建

把 scripts/example_build.py 和 scripts/workflow.py 复制到任务输入状态旁，在合适环境安装 requirements-dev.txt。明确传入 --source、--state 和 --output。范例只读输入状态，输出 PDF、<output>.state.json 及 <output>.font-runs.json；输出状态包含实际绘制边界且 qc 已清空。审计和渲染使用该输出状态，不使用带旧边界的输入状态。

每块需要输出左上坐标的 target_bbox、完整 translation 及 status；表格读取 table.translated_rows，可有 col_proportions 和 spans [x0,y0,x1,y1]，并提供同形 source_rows。reading_order 列出块 ID。字体记录 name、source 路径、sha256、purpose，可有 face_index；block.font 指定首选字体。构建器逐缺字选择已验证的备用字体并记录实际使用者及 fallback_from，不能以字体集合的覆盖代替选中字体覆盖。格式不支持时明确未验证或失败。

范例支持未旋转、未裁切、零原点页面上的段落、sub/sup 标记及真实表格。遇到 pending 块、无效映射、覆盖原文、缺字和溢出就停止。通过全书单一 overlay 共享字体，由 ReportLab 子集化，压缩内容流并清理废弃对象。复杂数学、图形布局、旋转/裁切标准化及重叠设计由任务构建器处理，输出必须查看。

执行 check-fonts OUTPUT.state.json --assignments OUTPUT.font-runs.json --out fonts.json。自定义构建器输出同样结构：schema_version:1、output_sha256，以及包含 page、block、font、text、可选 fallback_from 的 runs。片段须来自实际绘制，按顺序覆盖每块渲染文字和完整表格单元格，字体名称对应登记表。声明片段覆盖通过不证明 PDF 嵌入或字形显示正确。

恢复验证时将状态、构建器及辅助模块复制到独立目录，标明外部原文和字体依赖并在那里重建。修改副本一段文字及一个单元格，确认提取/渲染结果变化且输入没有被重置。不改数据重复构建两次，对比字节/资源，不能累积资源。恢复说明记录依赖和命令，不为了测试而修改已验收包。

构建器保留并核对已声明的 layout.inputs，输出状态记录实际 Python、pypdf 和 ReportLab 版本。跨环境重建若字节不同，核对绘制指令、文字、资源及渲染结果，并记录具体原因；重复运行仍应稳定，不能仅因视觉相同就忽略不明差异。
