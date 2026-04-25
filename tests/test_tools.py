import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.tools import get_tool, list_available_tools
from app.tools.code_tool import CodeTool
from app.tools.doc_tool import DocTool
from app.tools.learning_path_tool import LearningPathTool
from app.tools.paper_tool import PaperTool
from app.tools.repo_index_tool import RepoIndexTool
from app.tools.sandbox_tool import SandboxTool
from app.tools.schedule_tool import ScheduleTool, _ScheduleStorage
from app.tools.source_tool import SourceTool
from app.tools.test_tool import TestTool
from app.tools.wiki_tool import WikiTool


class CodeToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = CodeTool()

    def test_code_tool_success(self):
        result = self.tool.execute(command="python -c \"print('hello')\"", timeout=10)
        self.assertTrue(result.success)
        self.assertIn("hello", result.output)
        self.assertEqual(result.metadata.get("returncode"), 0)

    def test_code_tool_blocks_dangerous_command(self):
        result = self.tool.execute(command="rm -rf /")
        self.assertFalse(result.success)
        self.assertIn("Blocked potentially dangerous command", result.error)


class WikiToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = WikiTool()

    @patch("app.tools.wiki_tool.requests.get")
    def test_wiki_tool_success_with_mocked_http(self, mock_get):
        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            "query": {"search": [{"title": "Transformer (deep learning model)"}]}
        }

        summary_response = MagicMock()
        summary_response.raise_for_status.return_value = None
        summary_response.json.return_value = {
            "title": "Transformer (deep learning model)",
            "extract": "A transformer is a deep learning architecture.",
        }

        mock_get.side_effect = [search_response, summary_response]

        result = self.tool.execute(query="transformer", lang="en")
        self.assertTrue(result.success)
        self.assertIn("Transformer", result.output)
        self.assertEqual(result.metadata.get("lang"), "en")

    def test_wiki_tool_requires_query(self):
        result = self.tool.execute()
        self.assertFalse(result.success)
        self.assertIn("query", result.error)


class ScheduleToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tool = ScheduleTool()
        storage_path = Path(self.temp_dir.name) / "schedule_store.json"
        self.tool._storage = _ScheduleStorage(path=storage_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schedule_create_and_get_plan(self):
        created = self.tool.execute(action="create_plan", goal="Reproduce a paper", tasks=["Task A", "Task B"])
        self.assertTrue(created.success)
        plan_id = created.metadata.get("plan_id")
        self.assertIsNotNone(plan_id)

        loaded = self.tool.execute(action="get_plan", plan_id=plan_id)
        self.assertTrue(loaded.success)
        self.assertIn("Reproduce a paper", loaded.output)

    def test_schedule_increase_timeout(self):
        result = self.tool.execute(action="increase_timeout", current_timeout=20, factor=2)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata.get("recommended_timeout"), 40)


class LearningPathToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = LearningPathTool()

    def test_learning_path_generate_markdown(self):
        result = self.tool.execute(topic="paper reproduction", level="beginner", weeks=4)
        self.assertTrue(result.success)
        self.assertIn("Learning Path", result.output)

    def test_learning_path_invalid_level(self):
        result = self.tool.execute(topic="topic", level="expert")
        self.assertFalse(result.success)


class RegistryTests(unittest.TestCase):
    def test_registry_contains_expected_tools(self):
        tools = list_available_tools()
        self.assertIn("paper_tool", tools)
        self.assertIn("source_tool", tools)
        self.assertIn("repo_index_tool", tools)
        self.assertIn("sandbox_tool", tools)
        self.assertIn("test_tool", tools)
        self.assertIn("doc_tool", tools)
        self.assertIn("code_tool", tools)
        self.assertIn("wiki_tool", tools)
        self.assertIn("schedule_tool", tools)
        self.assertIn("learning_path_tool", tools)

        self.assertIsNotNone(get_tool("code_tool"))


class PaperToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = PaperTool()

    def test_extract_from_text(self):
        text = """
        A Great Paper Title
        Abstract
        This work improves accuracy on CIFAR-10.
        Method
        We use a transformer approach.
        Experiments
        Accuracy is the target metric.
        """
        result = self.tool.execute(action="extract_from_text", text=text)
        self.assertTrue(result.success)
        paper = result.metadata.get("paper", {})
        self.assertIn("title", paper)
        self.assertIn("datasets", paper)

    def test_resolve_identifier(self):
        result = self.tool.execute(action="resolve_identifier", identifier="10.1000/xyz123")
        self.assertTrue(result.success)
        self.assertIn("doi.org", result.output)


class SourceToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = SourceTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "README.md").write_text("demo", encoding="utf-8")
        (self.root / "requirements.txt").write_text("requests", encoding="utf-8")
        (self.root / "main.py").write_text("print('hi')", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_candidates(self):
        text = "Code: https://github.com/example/project and paper: https://arxiv.org/abs/1234.5678"
        result = self.tool.execute(action="discover_candidates", text=text)
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.metadata.get("count", 0), 2)

    def test_analyze_source(self):
        result = self.tool.execute(action="analyze_source", source_path=str(self.root))
        self.assertTrue(result.success)
        completeness = result.metadata.get("completeness", {})
        self.assertTrue(completeness.get("has_readme"))


class RepoIndexToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = RepoIndexTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "module.py").write_text("def fn():\n    return 'ok'\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_tree(self):
        result = self.tool.execute(action="index_tree", root_path=str(self.root))
        self.assertTrue(result.success)
        self.assertGreater(result.metadata.get("count", 0), 0)

    def test_read_file(self):
        result = self.tool.execute(action="read_file", root_path=str(self.root), path="module.py")
        self.assertTrue(result.success)
        self.assertIn("def fn", result.output)


class SandboxToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = SandboxTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "requirements.txt").write_text("requests", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_environment(self):
        result = self.tool.execute(action="detect_environment", project_path=str(self.root))
        self.assertTrue(result.success)
        env = result.metadata.get("environment", {})
        self.assertIn("python", env.get("detected_runtimes", {}))


class TestToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = TestTool()

    def test_compare_metrics(self):
        result = self.tool.execute(
            action="compare_metrics",
            expected={"accuracy": 0.90},
            actual={"accuracy": 0.905},
            tolerance=0.02,
        )
        self.assertTrue(result.success)

    def test_run_command(self):
        result = self.tool.execute(action="run_command", command="python -c \"print('ok')\"", timeout=30)
        self.assertTrue(result.success)


class DocToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = DocTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_write_document(self):
        output_path = self.root / "report.md"
        result = self.tool.execute(
            action="write_document",
            output_path=str(output_path),
            title="Test Report",
            content="hello",
        )
        self.assertTrue(result.success)
        self.assertTrue(output_path.exists())

    def test_generate_repro_report(self):
        output_path = self.root / "final_report.md"
        result = self.tool.execute(
            action="generate_repro_report",
            output_path=str(output_path),
            goal="复现测试",
            paper={"title": "demo"},
            source={"repo": "x"},
            environment={"python": "3.11"},
            tests={"status": "ok"},
            summary="完成",
        )
        self.assertTrue(result.success)
        self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
