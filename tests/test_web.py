from pathlib import Path

import pytest
from PIL import Image


def _card_png(path: Path, color="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 84), color).save(path)
    return path


def _app(tmp_path, password="secret"):
    from mtgproxy.web import create_app
    from mtgproxy.catalog import Catalog

    db = tmp_path / "catalog.db"
    images = tmp_path / "images"
    sheets = tmp_path / "sheets-root"
    sheets.mkdir()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "PASSWORD": password,
            "DB_PATH": db,
            "IMAGES_DIR": images,
            "SHEETS_ROOT": sheets,
        }
    )
    return app


def _client(tmp_path, password="secret"):
    app = _app(tmp_path, password=password)
    return app, app.test_client()


def test_create_app_rejects_empty_password(tmp_path):
    from mtgproxy.web import create_app

    with pytest.raises(ValueError, match="password"):
        create_app(
            {
                "SECRET_KEY": "x",
                "PASSWORD": "",
                "DB_PATH": tmp_path / "c.db",
                "IMAGES_DIR": tmp_path / "img",
                "SHEETS_ROOT": tmp_path,
            }
        )


def test_unauthenticated_root_redirects_to_login(tmp_path):
    _, client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
