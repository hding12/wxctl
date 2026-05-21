from __future__ import annotations

from wxctl.adapters.wechat_fs import find_db_storage_dir


def test_find_db_storage_dir_under_account_root(tmp_path):
    db_storage = tmp_path / "wxid_test_1234" / "db_storage"
    db_storage.mkdir(parents=True)
    assert find_db_storage_dir(tmp_path) == db_storage


def test_find_db_storage_dir_accepts_direct_path(tmp_path):
    db_storage = tmp_path / "db_storage"
    db_storage.mkdir()
    assert find_db_storage_dir(db_storage) == db_storage
