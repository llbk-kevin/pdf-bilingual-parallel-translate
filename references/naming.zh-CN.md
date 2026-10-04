# 文档身份与命名

为任何原文、双语译本或任务目录命名前读取本参考。只有确认属于 TI 的文档才应用 TI 补充规则。

## 先识别再命名

检查封面、前几页、页脚及出版信息页，识别实际标题、文献编号和版本。元数据及下载文件名只作线索。在 state.document.naming 或任务命名清单中保存完整标题、选用标题、中文标题、编号、版本、语言、适用的厂商、文件角色及页码/证据说明。对于已经验收的历史状态，新增命名依据保存在迁移清单中，避免改变已绑定指纹的内容。

使用实际原文语言的标题，包括非英文标题，不额外生成英文中间标题。保留原有大小写及属于标题的型号。整理换行及已确认的断行连字符。过长副标题可以省略，但证据中保留完整标题；不得静默删减主标题含义。

文献编号必须属于本文，不能用器件型号、参考文献、参考设计、日期或下载文件名中拼接的数字替代。非 TI 编号保留官方写法，包括数字及连字符。省略无法确认的编号及相邻分隔符。论文即使有文章编号或 DOI，文件名也省略编号字段，相关信息保留在依据中。

## 格式与文件角色

| 角色 | 文件名 |
| --- | --- |
| 非中文原文 | `<number>_<original title>_<Chinese title><optional version>.pdf` |
| 生成的双语译本 | `<number>_<original title>_<Chinese title><optional version>_双语左右对照翻译.pdf` |
| 中文原文或一般官方中文文档 | `<number>_<Chinese original title><optional version>.pdf` |
| TI 官方中文文档 | `<English number>_<Chinese number>_<official Chinese title><optional version>.pdf` |

省略缺失的编号字段。中文原文只保留一次标题。文内确认的版本用全角括号附在中文标题后，例如（Rev1.7）或（V3.5）；不把日期自动当作版本。已有相同版本只保留一次。只有生成的双语译本添加翻译后缀，且仅加一次。修正已有误导性后缀前，先根据实际内容和来源确定文件角色。

原文位于任务目录旁，任务目录使用原文文件名主体，目录内的生成译本在该主体后增加翻译后缀。遵循用户明确指定的输出目录。不得覆盖原文或已存在的目标。

## TI 补充规则

已确认的 TI 文献编号转为小写并保留修订字母，例如 SLVA317B 变为 slva317b。编号从本文读取，不从参考文献列表取用。TI 官方中文文档依据明确的 English Document 标识确定英文编号；只省略缺失的编号字段。官方中文文档不添加生成译本后缀，也不因命名而重新翻译。

~~~text
原文：snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器.pdf
译本：snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器_双语左右对照翻译.pdf
官方中文：snvaa43_zhcace2_耦合电感器SEPIC功率级的基本计算.pdf
~~~

## 格式化辅助函数

scripts/workflow.py 提供 document_filename(source_title, chinese_title, document_id=None, *, role, version=None, source_is_chinese=False, paper=False, vendor=None, english_document_id=None)。role 必填，可选 original、generated-translation 或 official-chinese。中文原文设置 source_is_chinese=True，论文设置 paper=True，vendor='TI' 启用 TI 编号规范化。函数只格式化已确认的元数据并返回一个文件名，不识别文档或执行改名。

TI 包装入口 ti_filename(english_title, chinese_title, document_id=None, *, role, english_document_id=None, version=None) 也改为必须提供 role。旧的隐式角色调用及 official_chinese 布尔参数需改为显式角色。缺失角色会报错，不静默选择后缀。

~~~python
from workflow import document_filename
original = document_filename('Eight Hints for Better Scope Probing',
    '改善示波器探测的八项提示', '5989-7894EN', role='original')
translated = document_filename('Eight Hints for Better Scope Probing',
    '改善示波器探测的八项提示', '5989-7894EN', role='generated-translation')
~~~

规范化空白并最小替换 Windows 非法字符：英文冒号替换为两侧带空格的连字符，斜杠替换为全角斜杠，去除结尾空格和点。辅助函数拒绝 Windows 保留文件名及超过 255 个 UTF-16 代码单元的名称，不执行截断。Agent 还须检查完整路径长度、实际工具支持及目标冲突。

Windows 进程启动可能限制工作目录长度，即使文件读写已经支持长路径。遇到此情况，从较短的工作目录启动，使用完整路径传入构建器、状态、原文和输出；不因此自行截短已确认的标题。

## 提议、澄清与执行

每份文档翻译前主动检查命名，对原文、需要改名的既有译本及任务目录展示精确的新旧名称表，注明角色和理由。普通模式确认具体表格后改名；已接受的 Plan 包含表格时无需再次确认。等待命名选择时可继续独立翻译。新输出按已选格式命名，不额外设置改名批准。

拟定名称与实际文件角色矛盾、编号来源或版本不明确、或必须缩短主标题时，先说明具体冲突并询问，再决定名称。问题解决后在已说明的范围内使用答复。未经明确要求，不将一次任务特例升级为长期技能规则。

移动前保存精确路径与指纹，检查冲突及实际解析的目录边界，必要时用隔离样例验证长路径支持。逐组移动并持久保存断点，不使用广泛通配符改名或静默覆盖。更新当前恢复路径、重新生成说明、队列和交付索引。按照 [state-and-qc.zh-CN.md](state-and-qc.zh-CN.md) 保留原始审计/查看记录字节及每次历史迁移快照。核对 PDF 字节不变，重建仅在独立副本中测试。明确识别的历史记录不得纳入批量路径替换。

保留既有译稿，除非明确要求删除精确目标。命名规则不授权自动删除旧译稿。
