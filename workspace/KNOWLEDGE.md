# System Knowledge Base
# 系统知识库 - 业务规则和常识
# 此文件的内容会自动加载到系统提示词中，Agent 每次执行时都会参考。
# 您可随时编辑此文件来添加新的业务规则。

## 日期与报表规则 (Date & Report Rules)

- 销售日报 (Daily Sales Report) 永远在**第二天**发送。
  - 问"昨天的销售数据" → 搜索**今天**收到的报告
  - 问"今天的销售report" → 指的是**昨天**的业绩表现（即今天收到的report）
  - 问"某日期的业绩/数据" → 对应报告的收件日期 = 该日期 + 1天
- 周报通常在下周一发送。

## 邮件习惯 (Email Conventions)

- 用户日常使用的邮箱: DAVIDLIU@valueretailchina.com
- 搜索"最近一次XX发给我的邮件"时：先在 Inbox 搜索
- 搜索"我怎么回复的"时：在 Sent Items (已发送) 文件夹中搜索
- 常见同事邮箱格式: 名字+姓@valueretailchina.com

## 通用规则 (General Rules)

- 当用户说"帮我找邮件"但没指定文件夹时，默认搜索 Inbox
- 当邮件搜索没有结果时，尝试放宽搜索条件（去掉日期限制或扩大日期范围）
- 不要在任务未完成时询问用户"是否保存到知识库"
