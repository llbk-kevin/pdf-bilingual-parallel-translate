# 状态驱动的构建

通过 pipeline prepare 生成完整冻结环境及 v3 状态，按返回的 command_prefix/runner 依次执行 apply、build、verify、review、publish。构建读取保存译文并生成 PDF、状态及字体分配文件；几何和字段见 [inplace.zh-CN.md](inplace.zh-CN.md)。

## 工作文件与发布

输入状态和构建器放在 <source-stem>/recovery/，候选 PDF、构建伴随文件、提取、渲染及审计报告放在 <source-stem>/work/。构建始终在工作文件夹内进行，因为构建器会在 PDF 旁生成伴随文件；不要直接构建到外层交付路径。交付说明.md 保留在 <source-stem>/ 内。按需恢复的 PDF 及全部配套文件写入该文件夹的 work/rebuild/accepted.rebuilt.pdf。pipeline publish 返回对应的 notes 与 recovery_argv；状态位置非标准时使用 --task-dir。普通交付核对恢复依赖，不执行完整重建。

冻结的候选版本通过翻译、视觉和结构验收后：

1. 用 pipeline publish 检查成品路径和目标冲突，按相同字节发布，并核对成品 SHA-256。草稿留在 work/。
2. 构建前确定原文、字体、状态和证据的路径。参与指纹的路径发生变化时，按 [状态与审核证据](state-and-qc.zh-CN.md) 重新构建并检查。
3. publish 更新 output.path 并保留原审核证据，再运行最终一致性检查。交付说明及发布记录保存在工作文件夹。

已验收 PDF 必须嵌入独立阅读、渲染、搜索和复制所需的字体及资源。恢复文件用于编辑和验证，不是 PDF 的运行依赖。验证交付目录时，使用可丢弃的副本，只移除经过路径核验的副本工作文件夹，并确认两个 PDF 仍可渲染、提取文字且结果不变。不自动删除用户的工作文件夹。

## 默认原位布局

在 v3 状态中编辑来源 glyph IDs、method、translation、allowed_bbox、字体设置和明确的覆盖区域。target_bbox 及实际绘制位置由构建器生成，不另行编排一套独立页面布局。原表格网格及公式保留在复用内容中。正文按语义组合，保留单元格对应关系，仅对受影响的块设置有界字号拟合。源几何、图片共享、支持的链接、覆盖及失败处理见 [inplace.zh-CN.md](inplace.zh-CN.md)。

从多份源文件合订样张时，保留样本页到原文件页的映射及原文件 SHA-256。检查原文件到合并样本的链条，包括图片语义、链接与渲染。交付时列明抽取的源页，以及因目标页未入选而省略的链接。

## 通用字体与恢复验证

执行 check-fonts OUTPUT.state.json --assignments OUTPUT.font-runs.json --out fonts.json。自定义构建器输出同样结构：schema_version:1、output_sha256，以及包含 page、block、font、text、可选 fallback_from 的 runs。片段须来自实际绘制，字体名称对应登记表，并按顺序覆盖每个新增绘制块及完整译后单元格。v3 preserve 块不产生新增绘制片段。在渲染结果中检查实际字形。

恢复验证时将状态、构建器及辅助模块复制到独立目录，标明外部原文和字体依赖并在那里重建。修改副本中一个实际存在的译文块；有表格时再修改一个单元格，确认提取/渲染结果变化且输入没有被重置。纯文字文档无需为此检查新增表格。不改数据重复构建两次，对比字节/资源，不能累积资源。恢复说明记录依赖和命令，不为了测试而修改已验收包。

构建器核对已声明的 layout.inputs，并在生成状态记录 PyMuPDF 版本。恢复说明记录实际解释器及相关依赖版本。跨环境重建若字节不同，核对绘制指令、文字、资源及渲染结果，并记录具体原因；重复运行仍应稳定，不能仅因视觉相同就忽略不明差异。
