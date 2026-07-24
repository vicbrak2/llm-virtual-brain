from pathlib import Path

from fastapi.testclient import TestClient

from brain.server import create_app


def test_studio_facade_serves_public_team_page(tmp_path):
    app = create_app("profiles", str(tmp_path / "data"))
    client = TestClient(app)

    response = client.get("/studio")

    assert response.status_code == 200
    assert "Qamiluna Studio" in response.text
    assert "const PROFILE = 'qamiluna_team'" in response.text
    assert "/api/chat" in response.text
    assert "/api/profiles" not in response.text
    assert "/api/profile/delete" not in response.text
    assert '<script src="' not in response.text
    assert "createRoot" not in response.text


def test_studio_manifest_and_icons_are_available(tmp_path):
    app = create_app("profiles", str(tmp_path / "data"))
    client = TestClient(app)

    manifest = client.get("/studio/manifest.json")
    icon = client.get("/icons/qamiluna-icon-192.png")

    assert manifest.status_code == 200
    assert manifest.json()["start_url"] == "/studio"
    assert icon.status_code == 200
    assert icon.headers["content-type"] == "image/png"
    assert Path("ui/icons/qamiluna-icon-192.png").is_file()
