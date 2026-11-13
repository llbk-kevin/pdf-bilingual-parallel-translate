# 技能维护

## 仓库与安装

在 llbk-kevin/pdf-bilingual-parallel-translate 的 main 分支维护技能。安装入口为 <CODEX_HOME>/skills/pdf-bilingual-parallel-translate。由 CC Switch 托管时，先解析链接，在实际目录修改，再核对链接类型、目标和入口内容。未托管的普通目录直接维护。发现断链或独立副本分歧时先报告。

## 验证与提交

同步 SKILL.md、README.md 以及被修改的中英文配对参考，保持命令、字段和示例等价。文本使用 UTF-8 无 BOM。检查 Markdown 链接和 agents/openai.yaml，并在可用时运行 skill-creator 校验器。

在合适的环境安装 requirements-dev.txt，从仓库运行：

~~~text
python -m unittest discover -s tests -v
python scripts/pipeline.py --help
python scripts/pdf_tools.py --help
~~~

测试用代码生成 PDF 和字体。行为变更运行相关回归。修改坐标时检查页尺寸及左侧原文隔离，修改资源时检查编码图片和蒙版，修改流程时检查审核复用及发布路径。如需可视样例，运行 tests/generate_layout_samples.py --out <仓库外目录> --font <允许使用的中文字体>。字体集合可用 --face-index 选面。

用户原文、译本、渲染图、恢复文件、字体和凭据留在仓库之外。按 AGENTS.md 规范提交并正常推送 origin/main。

## 实现约束

- 压缩非图片流，保留原图片编码。审计遍历可达资源，检查图片编码流及显示语义。升级 pypdf 大版本时复核编码流清点。
- 在 PDFium 内存渲染副本中规范化 UserUnit，两侧比较使用相同矩阵和像素原点。
- 使用源文字绘制 trace 和 fontTools 译文字形轮廓判断删除范围及碰撞边界。字体序列化关闭时间戳重算，保证重复构建稳定。
- 读取原始 PDF 目标数组，保留 XYZ 的空坐标。几何和交互细节见 [inplace.zh-CN.md](inplace.zh-CN.md)。

发现具体缺陷时补充针对性回归。单次任务的验证记录留在任务目录。
