import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker

from backend import main, services, worker
from backend.db import Base, get_db, make_engine


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    sessions = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    config = replace(main.settings, data_dir=tmp_path, api_key="", demo_enabled=True)
    for module in (main, services, worker):
        monkeypatch.setattr(module, "settings", config)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(worker, "SessionLocal", sessions)

    def database():
        with sessions() as db:
            yield db

    main.app.dependency_overrides[get_db] = database
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def source(client):
    response = client.post("/api/v1/sources", json={
        "name": "测试路段", "latitude": 22.28, "longitude": 114.16, "baseline_speed": 60,
    })
    assert response.status_code == 201
    return response.json()


@pytest.fixture()
def image_bytes():
    data = io.BytesIO()
    Image.new("RGB", (120, 80), (120, 130, 140)).save(data, "PNG")
    return data.getvalue()
