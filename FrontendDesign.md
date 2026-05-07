# 论文复现助手（Paper Reproduction Agent）前端设计 Prompt

设计一个现代化的 AI Agent Chat 前端，用于“论文复现 / 实验执行”场景。

整体体验应类似 ChatGPT / Claude 的聊天界面，但增加一个“可观测执行过程（Execution Layer）”。

核心原则：

* 主界面仍然是自然聊天
* 用户与 AI 正常对话
* AI 可以判断：

  * 是简单问答
  * 还是需要进入 Agent 执行模式
* 执行过程不直接混入 assistant 回复
* 所有执行细节放入独立的可折叠 Execution 面板

---

# 整体布局

采用三部分结构：

## 1. Sidebar

包含：

* 历史会话
* 新建会话
* 设置
* 模型选择

风格参考 ChatGPT / Claude。

---

## 2. Main Chat Area（主聊天区）

保持干净、简洁。

这里只显示：

* 用户消息
* assistant 自然语言回复

assistant 回复应偏“总结”和“沟通”，而不是输出大量日志。

不要把：

* shell 输出
* traceback
* tool logs
* planning
* runtime details

直接塞进 assistant message。

聊天区必须保持“conversation-first”。

---

## 3. Execution Panel（执行层）

这是系统核心特色。

用于展示：

* agent steps
* tool calls
* terminal output
* runtime status
* artifacts

风格：

* 默认折叠
* 灰色小字
* 弱视觉层级
* 类似 ChatGPT 的“深度思考”
* 类似 agent timeline

例如：

```text id="bx6u50"
▼ Execution (8 steps)

✓ 解析论文
✓ 提取实验配置
✓ 搜索官方实现
⏳ 安装依赖
```

Execution 不应抢占主视觉焦点。

---

# Step 与 Terminal 分层

必须明确区分：

## Step（语义步骤）

表示 Agent “正在做什么”。

例如：

* 下载仓库
* 安装依赖
* 启动训练
* 修复 CUDA 冲突

这是高层、可解释的信息。

---

## Terminal Output（运行日志）

表示真实 stdout/stderr。

例如：

```bash id="kt39qj"
Collecting torch...
ERROR: CUDA mismatch
```

Terminal 属于某个 Step。

默认隐藏，可展开查看。

不要把 terminal 直接平铺在聊天区。

---

# Streaming 效果

Execution 必须支持实时动态更新：

```text id="pnk9se"
✓ 下载仓库
⏳ 安装依赖
```

随后自动更新为：

```text id="9ahwwz"
✓ 安装依赖
```

terminal 输出也应流式追加。

---

# Artifact 展示

执行完成后，支持展示实验产物：

* config.yaml
* checkpoint.pt
* train_curve.png
* evaluation.json

支持：

* 文件列表
* 图片预览
* 下载入口

---

# UI 风格

整体风格：

* 极简
* 现代
* 大量留白
* 类似 ChatGPT / Claude
* execution 使用：

  * 浅灰背景
  * 小字号
  * monospaced terminal
  * collapsible sections

不要做成：

* IDE
* DevOps Dashboard
* Hacker 风格终端

核心体验始终是：

# “对话优先（Conversation-first）”

Execution 是辅助观察层，而不是主内容。
