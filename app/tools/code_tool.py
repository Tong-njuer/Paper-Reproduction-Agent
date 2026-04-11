"""
代码题目工具 - 包含题目创建、代码评测、用户能力画像等功能
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from langchain.tools import tool
from langchain_openai import ChatOpenAI

from app.db.database import SessionLocal
from app.db.models import CodeProblem, UserCodeAnswer, UserAbility
from app.core.config import ZHIPU_API_KEY
from app.core.context import get_current_user_id

# Workspace 目录（用户隔离）
WORKSPACE_DIR = Path(__file__).parent.parent.parent / "workspace"


def _get_user_workspace() -> Path:
    """获取当前用户的工作目录"""
    user_id = get_current_user_id()
    if not user_id:
        return None
    user_dir = WORKSPACE_DIR / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _ensure_workspace():
    """确保 workspace 目录存在"""
    WORKSPACE_DIR.mkdir(exist_ok=True)


def _check_user():
    """检查用户是否登录"""
    user_id = get_current_user_id()
    if not user_id:
        return None, "用户未登录"
    return user_id, None


def _get_llm():
    """获取用于代码评测的LLM"""
    return ChatOpenAI(
        model="glm-5.1",
        openai_api_key=ZHIPU_API_KEY,
        openai_api_base="https://open.bigmodel.cn/api/paas/v4",
        temperature=0.3
    )


def _get_or_create_user_ability(user_id: int) -> UserAbility:
    """获取或创建用户能力画像"""
    with SessionLocal() as db:
        ability = db.query(UserAbility).filter(UserAbility.user_id == user_id).first()
        if not ability:
            ability = UserAbility(
                user_id=user_id,
                ability_tags=json.dumps({}),
                total_attempted=0,
                total_solved=0,
                updated_at=datetime.now().isoformat()
            )
            db.add(ability)
            db.commit()
            db.refresh(ability)
        return ability


def _update_ability_tags(user_id: int, problem_tags: list, grading_json: dict):
    """
    根据答题结果更新用户能力画像
    grading_json 包含: is_correct, error_type, coding_style_score, ability_update
    """
    ability = _get_or_create_user_ability(user_id)

    # 解析现有数据
    current_tags = json.loads(ability.ability_tags or "{}")
    error_history = json.loads(ability.error_history or "{}")
    is_correct = grading_json.get("is_correct", False)
    error_type = grading_json.get("error_type", "无错误")
    coding_style_score = grading_json.get("coding_style_score", 50)

    # 更新错误类型统计
    if error_type and error_type != "无错误":
        error_history[error_type] = error_history.get(error_type, 0) + 1

    # 更新代码风格得分（滑动平均）
    old_style = ability.coding_style_score or 50
    new_style = int((old_style * 0.7) + (coding_style_score * 0.3))
    ability.coding_style_score = new_style

    # 更新各标签的掌握程度
    ability_update = grading_json.get("ability_update", {})
    for tag, info in ability_update.items():
        tag = tag.strip()
        if not tag:
            continue

        level = info.get("level", "一般") if isinstance(info, dict) else info

        if tag not in current_tags:
            current_tags[tag] = {
                "level": level,
                "attempts": 1,
                "solved": 1 if is_correct else 0
            }
        else:
            current_tags[tag]["attempts"] = current_tags[tag].get("attempts", 0) + 1
            if is_correct:
                current_tags[tag]["solved"] = current_tags[tag].get("solved", 0) + 1

            # 根据正确率调整等级
            old_level = current_tags[tag].get("level", "一般")
            solved = current_tags[tag]["solved"]
            attempts = current_tags[tag]["attempts"]
            success_rate = solved / attempts if attempts > 0 else 0

            if success_rate >= 0.8:
                current_tags[tag]["level"] = "熟练"
            elif success_rate >= 0.4:
                current_tags[tag]["level"] = "一般"
            else:
                current_tags[tag]["level"] = "薄弱"

    ability.ability_tags = json.dumps(current_tags, ensure_ascii=False)
    ability.error_history = json.dumps(error_history, ensure_ascii=False)
    ability.total_attempted += 1
    if is_correct:
        ability.total_solved += 1
    ability.updated_at = datetime.now().isoformat()

    with SessionLocal() as db:
        db_ab = db.query(UserAbility).filter(UserAbility.user_id == user_id).first()
        db_ab.ability_tags = ability.ability_tags
        db_ab.error_history = ability.error_history
        db_ab.coding_style_score = ability.coding_style_score
        db_ab.total_attempted = ability.total_attempted
        db_ab.total_solved = ability.total_solved
        db_ab.updated_at = ability.updated_at
        db.commit()

    return current_tags


@tool
def create_code_problem(
    title: str,
    description: str,
    difficulty: str,
    tags: str,
    test_cases: str
) -> str:
    """
    创建一道新的代码题目，同时生成 workspace 文件供用户作答

    参数:
    - title: 题目名称
    - description: 题目描述（包含要求、输入输出示例等）
    - difficulty: 难度等级 (easy/medium/hard)
    - tags: 题目标签，JSON数组格式，如 '["数组", "链表"]'
    - test_cases: 测试用例，JSON数组格式，如 '[{"input": "1 2", "expected": "3"}]'
    """
    print("\n[DEBUG] create_code_problem CALLED")

    user_id, err = _check_user()
    if err:
        return err

    try:
        tags_list = json.loads(tags) if isinstance(tags, str) else tags
    except:
        tags_list = [tags]

    try:
        test_cases_list = json.loads(test_cases) if isinstance(test_cases, str) else test_cases
    except:
        return f"测试用例格式错误，请使用JSON数组格式"

    with SessionLocal() as db:
        problem = CodeProblem(
            user_id=user_id,
            title=title,
            description=description,
            difficulty=difficulty,
            tags=json.dumps(tags_list, ensure_ascii=False),
            test_cases=json.dumps(test_cases_list, ensure_ascii=False),
            created_at=datetime.now().isoformat()
        )
        db.add(problem)
        db.commit()
        db.refresh(problem)

        print(f"[DEBUG] Problem created: ID={problem.id}, title={title}")

    # 生成用户隔离的 workspace 文件
    _ensure_workspace()
    user_workspace = _get_user_workspace()
    test_cases_md = "\n".join(
        f"- 用例{i}: 输入: {tc.get('input', 'N/A')} → 期望输出: {tc.get('expected', 'N/A')}"
        for i, tc in enumerate(test_cases_list, 1)
    )

    workspace_content = f"""# {title}

**难度**: {difficulty}
**标签**: {", ".join(tags_list)}
**题目ID**: {problem.id}

---

## 题目描述

{description}

---

## 测试用例

{test_cases_md}

---

## 你的代码

```cpp
// 在此编写你的代码

```

---

*此文件由编程教练Agent自动生成 - 请在此文件编写代码，完成后对我说"提交第{problem.id}题答案"*
"""

    workspace_file = user_workspace / f"problem_{problem.id}.md"
    with open(workspace_file, "w", encoding="utf-8") as f:
        f.write(workspace_content)

    print(f"[DEBUG] Workspace file created: {workspace_file}")

    return f"""题目创建成功: [{problem.id}] {title} (难度: {difficulty}, 标签: {tags_list})

题目文件已生成: {workspace_file}
请在该文件中编写代码，完成后对我说"提交第{problem.id}题答案" """


@tool
def list_code_problems() -> str:
    """
    查询所有可用的代码题目
    """
    print("\n[DEBUG] list_code_problems CALLED")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        problems = db.query(CodeProblem).filter(CodeProblem.user_id == user_id).all()

        if not problems:
            return "目前没有任何代码题目"

        result_parts = []
        for p in problems:
            tags = json.loads(p.tags) if p.tags else []
            result_parts.append(
                f"[{p.id}] {p.title} (难度: {p.difficulty}, 标签: {', '.join(tags)})"
            )

        return "\n".join(result_parts)


@tool
def get_problem_detail(problem_id: int) -> str:
    """
    获取指定题目的详细信息（描述和测试用例）

    参数:
    - problem_id: 题目ID
    """
    print(f"\n[DEBUG] get_problem_detail CALLED, problem_id={problem_id}")

    user_id, err = _check_user()
    if err:
        return err

    with SessionLocal() as db:
        problem = db.query(CodeProblem).filter(
            CodeProblem.id == problem_id,
            CodeProblem.user_id == user_id
        ).first()

        if not problem:
            return f"未找到ID为 {problem_id} 的题目"

        tags = json.loads(problem.tags) if problem.tags else []
        test_cases = json.loads(problem.test_cases) if problem.test_cases else []

        result = [
            f"# {problem.title}",
            f"**难度**: {problem.difficulty}",
            f"**标签**: {', '.join(tags)}",
            f"\n## 题目描述\n",
            problem.description,
            f"\n## 测试用例\n"
        ]

        for i, tc in enumerate(test_cases, 1):
            result.append(f"用例{i}: 输入: {tc.get('input', 'N/A')} → 期望输出: {tc.get('expected', 'N/A')}")

        return "\n".join(result)


@tool
def submit_and_grade_code(problem_id: int) -> str:
    """
    提交代码并获取评测结果（从 workspace 文件读取用户代码）

    参数:
    - problem_id: 题目ID
    """
    print(f"\n[DEBUG] submit_and_grade_code CALLED, problem_id={problem_id}")

    user_id, err = _check_user()
    if err:
        return err

    # 从用户workspace文件读取用户代码
    user_workspace = _get_user_workspace()
    workspace_file = user_workspace / f"problem_{problem_id}.md"
    if not workspace_file.exists():
        return f"未找到题目文件: {workspace_file}，请确认题目ID是否正确"

    with open(workspace_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 从文件中提取用户代码（位于 ```cpp 和 ``` 之间的内容）
    code_match = re.search(r"```cpp\s*\n([\s\S]*?)\n```", content)
    if code_match:
        user_code = code_match.group(1).strip()
    else:
        # 尝试没有语言标记的情况
        code_match = re.search(r"```\s*\n([\s\S]*?)\n```", content)
        user_code = code_match.group(1).strip() if code_match else ""

    if not user_code:
        return "未在文件中找到你编写的代码，请确认已在 workspace 文件的【你的代码】区块中填写代码"

    with SessionLocal() as db:
        problem = db.query(CodeProblem).filter(
            CodeProblem.id == problem_id,
            CodeProblem.user_id == user_id
        ).first()

        if not problem:
            return f"未找到ID为 {problem_id} 的题目"

    tags = json.loads(problem.tags) if problem.tags else []
    test_cases = json.loads(problem.test_cases) if problem.test_cases else []

    grading_prompt = f"""你是一个代码评测专家。请全面评测用户的代码答案。

【题目信息】
标题: {problem.title}
描述: {problem.description}
测试用例:
{json.dumps(test_cases, ensure_ascii=False, indent=2)}

【用户提交的代码】
{user_code}

【评测要求 - 请从以下所有维度评测】

1. **正确性**: 代码是否能通过测试用例？逐个用例检查。对于未通过的用例，说明原因。
2. **错误类型分析**: 用户的代码属于哪种错误？
   - 语法错误: 代码无法编译/运行
   - 逻辑错误: 代码能运行但结果不对
   - 边界情况: 对特殊输入处理不当
   - 效率问题: 能跑但太慢/太占内存
3. **复杂度分析**: 时间复杂度和空间复杂度
4. **代码风格评分** (0-100分):
   - 命名规范 (30%): 变量/函数命名是否清晰
   - 代码结构 (30%): 缩进、分段、模块化
   - 注释说明 (20%): 关键逻辑是否有注释
   - 编程习惯 (20%): 避免硬编码、错误处理等
5. **知识点掌握度**: 用户对以下标签的掌握程度
   标签: {tags}

请以JSON格式返回评测结果：
{{
    "is_correct": true或false,
    "correctness_detail": "正确性详细说明，列出每个用例的通过情况",
    "error_type": "语法错误/逻辑错误/边界情况/无错误",
    "error_explanation": "错误原因说明（如果没有错误则为空）",
    "complexity_time": "时间复杂度",
    "complexity_space": "空间复杂度",
    "coding_style_score": 分数(0-100),
    "coding_style_detail": "代码风格详细评价",
    "ability_update": {{
        "标签名": {{
            "level": "熟练/一般/薄弱",
            "reason": "判断理由"
        }}
    }},
    "improvement_suggestions": ["具体可操作的改进建议1", "改进建议2"],
    "learning_resources": ["推荐学习资源1（如相关Wiki标题）", "资源2"]
}}

重要：
- ability_update 要基于用户在该标签题目上的表现综合判断
- improvement_suggestions 要具体指出代码中哪一行/哪个逻辑需要改进
- learning_resources 如果用户在某知识点薄弱，推荐相关的学习资源
"""

    try:
        llm = _get_llm()
        response = llm.invoke(grading_prompt)
        grading_result = response.content.strip()

        json_match = re.search(r"\{[\s\S]*\}", grading_result)
        if json_match:
            grading_json = json.loads(json_match.group())
        else:
            grading_json = {
                "is_correct": False,
                "correctness_detail": grading_result,
                "error_type": "无法分析",
                "error_explanation": "",
                "complexity_time": "无法分析",
                "complexity_space": "无法分析",
                "coding_style_score": 0,
                "coding_style_detail": "无法分析",
                "ability_update": {},
                "improvement_suggestions": ["请稍后再试"],
                "learning_resources": []
            }

    except Exception as e:
        print(f"[ERROR] Grading failed: {e}")
        grading_json = {
            "is_correct": False,
            "correctness_detail": f"评测过程出错: {str(e)}",
            "error_type": "无法分析",
            "error_explanation": "",
            "complexity_time": "无法分析",
            "complexity_space": "无法分析",
            "coding_style_score": 0,
            "coding_style_detail": "无法分析",
            "ability_update": {},
            "improvement_suggestions": ["请稍后再试"],
            "learning_resources": []
        }

    is_correct = grading_json.get("is_correct", False)
    tags_before_update = json.loads(_get_or_create_user_ability(user_id).ability_tags or "{}")

    # 传入完整 grading_json 以更新更丰富的数据
    new_tags = _update_ability_tags(user_id, tags, grading_json)

    tags_diff = {}
    for tag, info in new_tags.items():
        old_level = tags_before_update.get(tag, {}).get("level", "无记录") if isinstance(tags_before_update.get(tag), dict) else tags_before_update.get(tag, "无记录")
        new_level = info.get("level", "一般") if isinstance(info, dict) else info
        if old_level != new_level:
            tags_diff[tag] = f"{old_level} → {new_level}"
        elif old_level == "无记录":
            tags_diff[tag] = f"新增: {new_level}"

    answer_record = UserCodeAnswer(
        user_id=user_id,
        problem_id=problem_id,
        user_code=user_code,
        evaluation=json.dumps(grading_json, ensure_ascii=False),
        suggestions="\n".join(grading_json.get("improvement_suggestions", [])),
        is_correct=1 if is_correct else 0,
        submitted_at=datetime.now().isoformat()
    )
    with SessionLocal() as db:
        db.add(answer_record)
        db.commit()

    # 构建回复
    result_parts = [
        "【评测结果】",
        f"{'✅' if is_correct else '❌'} {'通过' if is_correct else '未通过'} - {grading_json.get('correctness_detail', 'N/A')}",
    ]

    # 错误类型分析
    error_type = grading_json.get("error_type", "")
    error_explanation = grading_json.get("error_explanation", "")
    if error_type and error_type != "无错误":
        result_parts.append(f"🔍 错误类型: {error_type}")
        if error_explanation:
            result_parts.append(f"   原因: {error_explanation}")

    # 复杂度
    time_complexity = grading_json.get("complexity_time", "N/A")
    space_complexity = grading_json.get("complexity_space", "N/A")
    result_parts.append(f"📊 复杂度: 时间 {time_complexity}, 空间 {space_complexity}")

    # 代码风格
    style_score = grading_json.get("coding_style_score", 0)
    style_detail = grading_json.get("coding_style_detail", "")
    result_parts.append(f"💡 代码风格得分: {style_score}/100")
    if style_detail:
        result_parts.append(f"   {style_detail}")

    # 能力标签变化
    if tags_diff:
        diff_str = ", ".join([f"{k}({v})" for k, v in tags_diff.items()])
        result_parts.append(f"🏷️ 能力变化: {diff_str}")

    # 改进建议
    suggestions = grading_json.get("improvement_suggestions", [])
    if suggestions:
        result_parts.append("\n【改进建议】")
        for sug in suggestions:
            result_parts.append(f"  • {sug}")

    # 推荐学习资源
    resources = grading_json.get("learning_resources", [])
    if resources:
        result_parts.append("\n【推荐学习资源】")
        for res in resources:
            result_parts.append(f"  📚 {res}")

    # 主动建议
    if not is_correct and resources:
        result_parts.append(f"\n👉 要不要我帮你创建相关学习资料？")

    print(f"[DEBUG] Grading completed: is_correct={is_correct}")

    return "\n".join(result_parts)


@tool
def get_user_ability_profile() -> str:
    """
    获取用户的能力画像（记录用户的编程能力长短板）
    """
    print("\n[DEBUG] get_user_ability_profile CALLED")

    user_id, err = _check_user()
    if err:
        return err

    ability = _get_or_create_user_ability(user_id)

    tags = json.loads(ability.ability_tags or "{}")
    error_history = json.loads(ability.error_history or "{}")

    result_parts = [
        "【用户能力画像】",
        f"📊 总答题数: {ability.total_attempted}",
        f"✅ 成功解题数: {ability.total_solved}",
        f"📈 解题成功率: {ability.total_solved/ability.total_attempted*100:.1f}%" if ability.total_attempted > 0 else "N/A",
        f"💡 代码风格均分: {ability.coding_style_score}/100" if ability.coding_style_score else "N/A",
    ]

    # 错误类型分析
    if error_history:
        result_parts.append("\n【错误类型分布】")
        for err_type, count in sorted(error_history.items(), key=lambda x: -x[1]):
            result_parts.append(f"  • {err_type}: {count}次")

    # 知识点掌握度
    if tags:
        result_parts.append("\n【各知识点掌握程度】")
        # 按熟练度分组
        strong = []
        medium = []
        weak = []
        for tag, info in tags.items():
            level = info.get("level", "一般") if isinstance(info, dict) else info
            attempts = info.get("attempts", 0) if isinstance(info, dict) else 0
            solved = info.get("solved", 0) if isinstance(info, dict) else 0
            if level == "熟练":
                strong.append((tag, attempts, solved))
            elif level == "一般":
                medium.append((tag, attempts, solved))
            else:
                weak.append((tag, attempts, solved))

        if strong:
            result_parts.append("  ✅ 熟练:")
            for tag, attempts, solved in strong:
                result_parts.append(f"     {tag} ({solved}/{attempts})")
        if medium:
            result_parts.append("  ⚠️ 一般:")
            for tag, attempts, solved in medium:
                result_parts.append(f"     {tag} ({solved}/{attempts})")
        if weak:
            result_parts.append("  ❌ 薄弱:")
            for tag, attempts, solved in weak:
                result_parts.append(f"     {tag} ({solved}/{attempts})")
    else:
        result_parts.append("\n  暂无能力记录")

    return "\n".join(result_parts)
