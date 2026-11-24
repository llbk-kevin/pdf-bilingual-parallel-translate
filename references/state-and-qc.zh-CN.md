# 状态与审核证据

## 状态与路径

使用 UTF-8 无 BOM JSON。[原位提取](inplace.zh-CN.md) 生成 schema_version: 3，layout.mode 为 inplace，layout.review_profile 为 practical 或 strict。使用[流程入口](practical.zh-CN.md)编辑和检查状态。源页和输出页都从 1 开始编号。原文区域采用裁剪、旋转及 UserUnit 生效后的可见页面左上角坐标，单位为点。构建器记录右侧实际绘制边界及其输出坐标。

相对路径从状态文件所在目录解析。编辑状态和冻结脚本放在 recovery/，候选与证据放在 work/，成品 PDF 放在工作目录旁。保留恢复所需的原文、字体及 layout.inputs。外部输入记录 path 和 sha256。指纹为实际文件字节的小写 SHA-256。

每页 expected_blocks 和 reading_order 与查看后确认的原文清单一致。无可译内容的页面及原样保留块须记录原因。原位表格通常使用 table-cell 块，分组表格记录逐格对应的 source_rows 和 translated_rows。图注和图内标签记录 figure_id。原文疑点记录 page、block、source_quote、concern 和 treatment。建议修正须附依据。

## 交付范围与显示页码

最终输出对交付范围内的每一页建立一一映射。完整交付覆盖全部源页。显式样本覆盖 document.selected_source_pages，并记录省略的跳转目标。局部预览可以少于交付范围，不能直接发布。

输出尺寸为 2W × H，原文区域为 [0,0,W,H]。印刷页码随原页图形保留。可选 layout.pagination_strategy 为 preserve-source 或 physical-total，使用时每页记录 pagination.source_label 和 pagination.text。preserve-source 记录已确认的原页码，未编号页用 null 和空文本。physical-total 仅适用于全书无印刷页码的文档，source_label 为 null，显示物理源页号/源文件总页数，封面和空白页均计入。

新绘制的页码须指定 id、输出可见左上角坐标中的 target_bbox、font_size 和可选字体。构建前在右侧预留可读区域。新页码参与碰撞检查和实际字体片段核验。显示页码与物理页索引分别记录。

## 指纹与审核

content_hash 包含 source、document、layout、glossary、pages 和 issues。输出字节与 qc 另行绑定。机械证据按候选、原文、比较状态、字体、字体分配和工具版本绑定。原文清点确认和实际观察独立登记，同一候选补记清点可复用原审计和图像。大型 v3 状态使用紧凑 UTF-8 JSON 并原子替换。参与指纹的输入变化后，从编辑状态重新构建并检查。共享字体、版式、术语、问题或相关上下文变化可能影响多页。practical 使用本页及声明的 context_pages。strict 默认考虑整份文档，除非已检查并明确声明上下文依赖。

verify 将确切输出绑定到审计、实际字体片段、字体报告和渲染索引。实际打开 review_needed 页面，再通过 review 登记观察。viewed 记录将源页、输出哈希、索引路径及哈希、渲染设置、图片与像素哈希、页面内容哈希绑定到实际查看者、时间及证据。reused 记录保留当前渲染哈希、原始 viewed 记录和复用理由。保留引用的两份索引及图片。像素、设置和页面依赖均匹配时方可复用。 观察文件携带 verify 返回的输出和渲染索引 SHA-256。部分候选观察也可用 --previous-state 逐页复用；某页记录缺失、重复或证据失效时，独立验证其余页面。

check-state --final 核对声明范围的页覆盖、实际查看记录、字体文件及分配、审计处置，以及原文、成品和构建器指纹。按验收模式说明相关警告和保留问题。修正失效输入后，用 review 保存真实观察。

## 发布与恢复

publish 按原字节复制成品，更新 output.path，保持证据与相同字节绑定。目录及按需恢复方法见 [building.zh-CN.md](building.zh-CN.md)。恢复时先核对原文指纹，再加载保存的译文、映射和布局决定。预检前确定文件名和目录，使状态引用稳定。

两份 PDF 各自包含阅读资源。工作目录保存可编辑状态和审核证据。用户删除工作目录后，须恢复这些文件才能重新检查状态或复用证据。

当前任务的 layout.runtime_launcher、layout.runtime_packages、layout.inputs 和 layout.fonts 必需，由 prepare 生成。output.assignments 明确记录字体分配文件路径，发布后仍从该路径读取。

## 作者分包与复核判断

apply/build 接收主文档或分包作者状态；verify/review/publish 接收候选状态；status/inspect 可读两者。候选记录精确 authoring_state 修复路径。发布生成已验收作者决定的 accepted.author.json，在 publication.json 记录指纹，恢复命令使用该快照，不改活跃作者状态。

import-package 核对清单、原文字节、分配页、页级基线及冻结依赖；依赖比较实际内容，不把相对路径重定位当作变化。仅导入明确白名单中的页级作者内容，候选绘制结果、QC、输出映射及包内路径不导入。重新提取并验证原文字形事实与归属；原子提交，相同最终结果重复导入无修改。冲突需重导受影响分包。

verify 生成已绑定的观察模板。实际查看页使用 pass 或 repair；pass 确认本页列出的清点／覆盖检查，并按生成 ID 明确解释每项可保留差异；repair 说明位置和原因，不计入有效通过覆盖。脚本从同一观察生成 review-summary.json 及就绪结果，不手工填写哈希和内部覆盖字段。
