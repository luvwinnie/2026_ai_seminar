import os
import tempfile
from pathlib import Path

import pytest

# database.py が読み込まれる前に、テスト用の一時 DB を指す（原本の data/ は読むだけ）
TEST_DB = Path(tempfile.mkdtemp(prefix="defect_test_")) / "test.db"
os.environ["DB_PATH"] = str(TEST_DB)
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # with で起動時の処理（表を作る → 取込 → マスタ）を動かす
    with TestClient(app) as c:
        yield c


def ids(response) -> list[str]:
    return [item["defect_id"] for item in response.json()["items"]]
