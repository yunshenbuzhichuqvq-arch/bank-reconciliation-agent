import os
from pathlib import Path


TEST_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_tests.sqlite")
TEST_MEMORY_DB_PATH = Path("/private/tmp/bank_reconciliation_agent_memory_tests.sqlite")

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
if TEST_MEMORY_DB_PATH.exists():
    TEST_MEMORY_DB_PATH.unlink()

os.environ["MYSQL_DSN"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["MEMORY_SQLITE_PATH"] = str(TEST_MEMORY_DB_PATH)
