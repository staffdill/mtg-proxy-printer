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


def test_wrong_password_stays_on_login(tmp_path):
    _, client = _client(tmp_path, password="correct")
    resp = client.post("/login", data={"password": "wrong"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"wrong" in resp.data.lower() or b"invalid" in resp.data.lower()
    # Still cannot see search
    resp2 = client.get("/")
    assert resp2.status_code == 302


def test_correct_password_reaches_search(tmp_path):
    _, client = _client(tmp_path, password="correct")
    resp = client.post("/login", data={"password": "correct"}, follow_redirects=True)
    assert resp.status_code == 200
    # After Task 4 this is the real search page; for now any 200 after login is ok
    # if root is no longer a redirect:
    resp2 = client.get("/")
    assert resp2.status_code == 200


def test_logout_clears_session(tmp_path):
    _, client = _client(tmp_path, password="correct")
    client.post("/login", data={"password": "correct"})
    client.get("/logout")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
