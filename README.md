# 乒乓球分组 Skill

用于整理赛事名单、随机分组、安排组内单循环，以及生成淘汰赛签位和公开对战图。

技能目录：[`table-tennis-draw`](table-tennis-draw)。完整使用规则见 [`SKILL.md`](table-tennis-draw/SKILL.md)。

## 包含的功能

- 按组数均衡分组，支持指定种子分别进入不同小组、固定组号。
- 生成组内单循环分轮对阵，核对每对选手只交手一次。
- 为 Excel 循环表提供比分录入和矩阵展示辅助模块。
- 编排每组前 2 名出线的单败淘汰赛，生成 PDF、PNG 对战图。
- 保存随机数参数、名单哈希及核验记录，便于复现抽签。

## 使用示例

在已加载此技能的助手中提供本次名单，并说明分组规则，例如：

```text
使用 $table-tennis-draw 处理这份名单。
分组个数：8
种子个数：4
种子人选：张三、李四、王五、赵六
种子强弱顺序：张三、李四、王五、赵六（由强到弱）
保护方式：这 4 名种子分别在不同小组。
淘汰赛：每组前 2 名出线，先生成第二名待抽签的预设图。
```

以上人名仅作示例。每次使用当前提供的名单，不沿用其他比赛数据；若只需要分组，可明确说明“只生成分组”。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `table-tennis-draw/SKILL.md` | 技能入口和工作流程 |
| `table-tennis-draw/agents/openai.yaml` | 技能显示名称和简介 |
| `table-tennis-draw/scripts/draw.py` | 均衡分组及核验 |
| `table-tennis-draw/scripts/round_robin.py` | 组内单循环对阵 |
| `table-tennis-draw/scripts/round_robin_tables.mjs` | Excel 循环赛工作表辅助模块 |
| `table-tennis-draw/scripts/knockout.py` | 淘汰赛签位及第二名抽签 |
| `table-tennis-draw/scripts/render_knockout.py` | PDF、PNG 公开对战图 |
| `table-tennis-draw/references/` | 输入格式、循环赛和淘汰赛说明 |

## 运行条件与范围

分组、循环赛和淘汰赛编排脚本仅使用 Python 3 标准库。生成对战图另需 `reportlab`、`pypdf`、Poppler 的 `pdftoppm` 和可用的中文字体；Windows 默认使用微软雅黑。Excel 辅助模块需由支持其 Workbook API 的表格运行环境调用，不是独立的 Excel 导出程序。

脚本输入及运行命令见以下说明：

- [名单格式与分组命令](table-tennis-draw/references/input-format.md)
- [组内循环赛](table-tennis-draw/references/round-robin.md)
- [淘汰赛编排与绘图](table-tennis-draw/references/knockout.md)

当前淘汰赛自动模式支持 1、2、4、8、16、32 组，每组前 2 名出线。同班回避、不均衡人数和其他淘汰赛制需另行编排。没有成绩时不自动填写胜负或名次。
