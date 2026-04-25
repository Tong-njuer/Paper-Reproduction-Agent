# Agent Demo 快速开始

本文档提供最小可执行路径：安装依赖、运行测试、启动 CLI 与 UI。

## 1. 环境准备

建议使用 Python 3.11。

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. 配置 API Key（可选）

如果你希望使用真实 LLM 推理，请在项目根目录创建 `.env`：

```env
ZHIPU_API_KEY=your_api_key_here
LLM_PROVIDER=zhipu
LLM_MODEL=glm-5.1
```

未配置时，Agent 仍可在 Demo/Fallback 逻辑下运行。

## 3. 运行测试

```bash
python -m unittest discover -s tests -v
```

预期：全部测试通过。

## 4. 启动命令行 Demo

```bash
python -m app.main --mode demo
```

指定目标运行：

```bash
python -m app.main --mode agent --goal "复现论文：Minimal learning machine for multi-label learning"
```

## 5. 启动 Web UI

推荐使用 streamlit 启动：

```bash
streamlit run app/streamlit_app.py
```

浏览器默认地址通常是 `http://localhost:8501`。

## 6. 论文复现工具链最小调用顺序

1. `paper_tool`：抽取论文结构与复现任务
2. `source_tool`：发现并获取源码
3. `repo_index_tool`：索引仓库并定位入口
4. `sandbox_tool`：创建隔离工作区和安装计划
5. `test_tool`：执行检查/测试/指标对比
6. `doc_tool`：落盘运行日志与最终报告

## 7. 常见问题

1. `ModuleNotFoundError: fitz`：执行 `pip install PyMuPDF`。
2. `streamlit` 命令不可用：执行 `pip install streamlit`。
3. API 未配置：可先用 demo 模式验证流程，再接入 `ZHIPU_API_KEY`。
