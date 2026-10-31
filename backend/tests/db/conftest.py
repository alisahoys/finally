"""Database test fixtures."""

import pytest

from db import connect, init_db


@pytest.fixture
def db_path(tmp_path):
    """Path to a freshly initialized database."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path):
    """Connection to a freshly initialized database."""
    connection = connect(db_path)
    yield connection
    connection.close()
