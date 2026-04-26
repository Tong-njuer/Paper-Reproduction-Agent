import json
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


FIXTURE_PAPER = Path(__file__).parent / "fixtures" / "synthetic_paper_with_code.md"


class RegistryOnlyTests(unittest.TestCase):
    def test_registry_contains_all_tools(self):
        tools = list_available_tools()
        expected = {
            "paper_tool",
            "source_tool",
            "repo_index_tool",
            "sandbox_tool",
            "test_tool",
            "doc_tool",
            "code_tool",
            "wiki_tool",
            "schedule_tool",
            "learning_path_tool",
        }
        self.assertTrue(expected.issubset(set(tools.keys())))
        self.assertIsNotNone(get_tool("paper_tool"))


class PaperToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = PaperTool()
        self.paper_text = FIXTURE_PAPER.read_text(encoding="utf-8")

    def test_extract_from_synthetic_paper(self):
        result = self.tool.execute(action="extract_from_text", text=self.paper_text)
        self.assertTrue(result.success)

        paper = result.metadata.get("paper", {})
        self.assertIn("LiteMLM", paper.get("title", ""))
        self.assertIn("cifar-10", [d.lower() for d in paper.get("datasets", [])])
        self.assertIn("accuracy", [m.lower() for m in paper.get("metrics", [])])
        self.assertGreater(len(paper.get("reproduction_tasks", [])), 0)

    def test_resolve_identifier_arxiv(self):
        result = self.tool.execute(action="resolve_identifier", identifier="2401.12345")
        self.assertTrue(result.success)
        self.assertIn("arxiv.org/abs/2401.12345", result.output)

    def test_extract_requires_input(self):
        result = self.tool.execute(action="extract")
        self.assertFalse(result.success)


class SourceToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = SourceTool()
        self.paper_text = FIXTURE_PAPER.read_text(encoding="utf-8")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "README.md").write_text("demo", encoding="utf-8")
        (self.root / "requirements.txt").write_text("requests", encoding="utf-8")
        (self.root / "main.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "tests").mkdir(parents=True, exist_ok=True)
        (self.root / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_candidates_from_synthetic_paper(self):
        result = self.tool.execute(action="discover_candidates", text=self.paper_text)
        self.assertTrue(result.success)
        candidates = result.metadata.get("candidates", [])
        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(any("github.com" in item.get("url", "") for item in candidates))

    def test_analyze_source(self):
        result = self.tool.execute(action="analyze_source", source_path=str(self.root))
        self.assertTrue(result.success)
        completeness = result.metadata.get("completeness", {})
        self.assertTrue(completeness.get("has_readme"))
        self.assertTrue(completeness.get("has_dependency_file"))

    def test_clone_repo_requires_args(self):
        result = self.tool.execute(action="clone_repo")
        self.assertFalse(result.success)


class RepoIndexToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = RepoIndexTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "pkg").mkdir(parents=True, exist_ok=True)
        (self.root / "pkg" / "model.py").write_text(
            "def train_model(x):\n    return x\n\n"
            "def evaluate_model(y):\n    return y\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_and_search(self):
        indexed = self.tool.execute(action="index_tree", root_path=str(self.root), max_depth=5)
        self.assertTrue(indexed.success)
        self.assertGreater(indexed.metadata.get("count", 0), 0)

        searched = self.tool.execute(action="search_text", root_path=str(self.root), query="train_model")
        self.assertTrue(searched.success)
        matches = searched.metadata.get("matches", [])
        self.assertTrue(any(item.get("path") == "pkg/model.py" for item in matches))

    def test_read_file_blocks_path_traversal(self):
        result = self.tool.execute(action="read_file", root_path=str(self.root), path="../secret.txt")
        self.assertFalse(result.success)


class SandboxToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = SandboxTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_workspace_and_detect_environment(self):
        created = self.tool.execute(
            action="create_workspace",
            base_dir=str(self.base),
            user_id="tester",
            run_id="run_tools_only",
        )
        self.assertTrue(created.success)

        root = Path(created.metadata["paths"]["root"])
        self.assertTrue(root.exists())
        (root / "requirements.txt").write_text("requests\n", encoding="utf-8")

        detected = self.tool.execute(action="detect_environment", project_path=str(root))
        self.assertTrue(detected.success)
        env = detected.metadata.get("environment", {})
        self.assertIn("python", env.get("detected_runtimes", {}))

    def test_build_install_plan(self):
        result = self.tool.execute(action="build_install_plan", detected_runtimes={"python": ["requirements.txt"]})
        self.assertTrue(result.success)
        self.assertIn("pip install -r requirements.txt", result.output)


class CodeToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = CodeTool()

    def test_run_safe_command(self):
        result = self.tool.execute(command="python -c \"print('tools_ok')\"", timeout=15)
        self.assertTrue(result.success)
        self.assertIn("tools_ok", result.output)

    def test_block_dangerous_command(self):
        result = self.tool.execute(command="rm -rf /")
        self.assertFalse(result.success)

    def test_invalid_cwd(self):
        result = self.tool.execute(command="python -c \"print('x')\"", cwd="./not_exists_dir_abc")
        self.assertFalse(result.success)


class TestToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = TestTool()

    def test_compare_metrics_pass(self):
        result = self.tool.execute(
            action="compare_metrics",
            expected={"accuracy": 0.90, "f1": 0.80},
            actual={"accuracy": 0.91, "f1": 0.79},
            tolerance=0.03,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.metadata.get("passed"))

    def test_compare_metrics_fail(self):
        result = self.tool.execute(
            action="compare_metrics",
            expected={"accuracy": 0.90},
            actual={"accuracy": 0.60},
            tolerance=0.01,
        )
        self.assertFalse(result.success)

    def test_run_command(self):
        result = self.tool.execute(action="run_command", command="python -c \"print('run_ok')\"", timeout=30)
        self.assertTrue(result.success)
        payload = result.metadata.get("result", {})
        self.assertEqual(payload.get("return_code"), 0)


class DocToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = DocTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_write_and_append_and_report(self):
        report_path = self.root / "report.md"
        write_result = self.tool.execute(
            action="write_document",
            output_path=str(report_path),
            title="Tools Report",
            content="content body",
        )
        self.assertTrue(write_result.success)
        self.assertTrue(report_path.exists())

        log_path = self.root / "logs" / "run.log"
        append_result = self.tool.execute(
            action="append_log",
            output_path=str(log_path),
            message="step done",
            level="info",
        )
        self.assertTrue(append_result.success)

        json_path = self.root / "artifact.json"
        json_result = self.tool.execute(
            action="write_json_artifact",
            output_path=str(json_path),
            payload={"status": "ok"},
        )
        self.assertTrue(json_result.success)
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["status"], "ok")

        repro_path = self.root / "repro.md"
        repro_result = self.tool.execute(
            action="generate_repro_report",
            output_path=str(repro_path),
            goal="Tools Only",
            paper={"title": "LiteMLM"},
            source={"repo": "https://github.com/example/litemlm"},
            environment={"python": "3.11"},
            tests={"status": "pass"},
            summary="all good",
        )
        self.assertTrue(repro_result.success)
        self.assertTrue(repro_path.exists())


class ScheduleToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = ScheduleTool()
        self.temp_dir = tempfile.TemporaryDirectory()
        storage_path = Path(self.temp_dir.name) / "schedule_store.json"
        self.tool._storage = _ScheduleStorage(path=storage_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_update_get_list(self):
        created = self.tool.execute(action="create_plan", goal="Reproduce LiteMLM", tasks=["step1", "step2"])
        self.assertTrue(created.success)
        plan_id = created.metadata.get("plan_id")

        updated = self.tool.execute(action="update_progress", plan_id=plan_id, task_id=1, status="completed")
        self.assertTrue(updated.success)

        loaded = self.tool.execute(action="get_plan", plan_id=plan_id)
        self.assertTrue(loaded.success)

        listed = self.tool.execute(action="list_plans")
        self.assertTrue(listed.success)
        self.assertGreaterEqual(listed.metadata.get("count", 0), 1)

    def test_increase_timeout(self):
        result = self.tool.execute(action="increase_timeout", current_timeout=20, factor=2)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata.get("recommended_timeout"), 40)


class LearningPathToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = LearningPathTool()

    def test_markdown_and_json_output(self):
        markdown_result = self.tool.execute(topic="paper reproduction", level="beginner", weeks=4)
        self.assertTrue(markdown_result.success)
        self.assertIn("Learning Path", markdown_result.output)

        json_result = self.tool.execute(
            topic="paper reproduction",
            level="intermediate",
            weeks=6,
            output_format="json",
        )
        self.assertTrue(json_result.success)
        plan = json.loads(json_result.output)
        self.assertEqual(plan.get("total_weeks"), 6)

    def test_invalid_level(self):
        result = self.tool.execute(topic="x", level="expert")
        self.assertFalse(result.success)


class WikiToolOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tool = WikiTool()

    @patch("app.tools.wiki_tool.requests.get")
    def test_wiki_success_with_mock(self, mock_get):
        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            "query": {"search": [{"title": "LiteMLM"}]}
        }

        summary_response = MagicMock()
        summary_response.raise_for_status.return_value = None
        summary_response.json.return_value = {
            "title": "LiteMLM",
            "extract": "LiteMLM is a synthetic benchmark paper.",
        }

        mock_get.side_effect = [search_response, summary_response]

        result = self.tool.execute(query="LiteMLM", lang="en")
        self.assertTrue(result.success)
        self.assertIn("LiteMLM", result.output)

    def test_wiki_requires_query(self):
        result = self.tool.execute()
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
