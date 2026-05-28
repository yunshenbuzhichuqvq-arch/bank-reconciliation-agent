import os
from pathlib import Path


TEST_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_tests.sqlite")

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["MYSQL_DSN"] = f"sqlite:///{TEST_DB_PATH}"
