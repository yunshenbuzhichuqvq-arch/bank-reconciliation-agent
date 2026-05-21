from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectSkeletonTest(unittest.TestCase):
    def test_mvp0_backend_skeleton_has_expected_entrypoints(self) -> None:
        expected_paths = [
            "src/bank_reconciliation_agent/main.py",
            "src/bank_reconciliation_agent/api/v1/reconcile.py",
            "src/bank_reconciliation_agent/api/v1/ledger.py",
            "src/bank_reconciliation_agent/api/v1/rag.py",
            "src/bank_reconciliation_agent/services/reconciliation.py",
            "src/bank_reconciliation_agent/agents/audit_agent.py",
            "src/bank_reconciliation_agent/rag/retriever.py",
            "src/bank_reconciliation_agent/db/schema.sql",
            "mock_data/README.md",
            "rules/reconciliation.md",
        ]

        missing_paths = [path for path in expected_paths if not (ROOT / path).exists()]

        self.assertEqual(missing_paths, [])

    def test_mvp0_routes_are_named_in_api_router(self) -> None:
        router_file = ROOT / "src/bank_reconciliation_agent/api/v1/router.py"

        self.assertTrue(router_file.exists())

        router_source = router_file.read_text(encoding="utf-8")
        self.assertIn("reconcile.router", router_source)
        self.assertIn("ledger.router", router_source)
        self.assertIn("rag.router", router_source)


if __name__ == "__main__":
    unittest.main()
