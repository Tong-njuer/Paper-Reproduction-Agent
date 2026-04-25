import unittest

from app.agent.planner import Plan, PlanStep, Planner
from app.agent.react import ReActEngine
from app.core.context import ExecutionContext


class ReActPromptingTests(unittest.TestCase):
    def setUp(self):
        self.react = ReActEngine()

    def test_build_prompt_contains_tool_usage_guide(self):
        plan = Plan(goal="demo", steps=[PlanStep(step_id=1, description="Extract paper")])
        step = plan.get_next_step()
        context = ExecutionContext(goal="demo")

        prompt = self.react._build_decision_prompt(step, plan, context)

        self.assertIn("Tool Usage Guide", prompt)
        self.assertIn("paper_tool", prompt)
        self.assertIn("test_tool", prompt)

    def test_parse_decision_sanitizes_unknown_action(self):
        plan = Plan(goal="demo", steps=[PlanStep(step_id=1, description="Extract paper")])
        step = plan.get_next_step()

        parsed = self.react._parse_decision(
            {
                "thought": "x",
                "action": "unknown_tool",
                "action_args": "not-a-dict",
            },
            step,
        )

        self.assertEqual(parsed.action, "idle")
        self.assertEqual(parsed.action_args, {})


class PlannerSchemaTests(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_parse_plan_response_extended_fields(self):
        steps = self.planner._parse_plan_response(
            {
                "steps": [
                    {
                        "step_id": 1,
                        "description": "Extract paper",
                        "depends_on": [],
                        "tool_hint": "paper_tool",
                        "expected_artifact": "paper_spec.json",
                        "acceptance_criteria": "title extracted",
                        "fallback_strategy": "ask user input",
                    }
                ]
            }
        )

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].tool_hint, "paper_tool")
        self.assertEqual(steps[0].expected_artifact, "paper_spec.json")
        self.assertEqual(steps[0].acceptance_criteria, "title extracted")
        self.assertEqual(steps[0].fallback_strategy, "ask user input")


if __name__ == "__main__":
    unittest.main()
