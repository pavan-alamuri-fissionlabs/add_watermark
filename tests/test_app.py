import pytest
import os
import sys

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from app import app

client = TestClient(app)

@pytest.fixture
def file_batch():
    return {
    "file_paths": [
        "/home/fl-lpt-690/Downloads/add_watermark/input/tsfae01.pdf",
        "/home/fl-lpt-690/Downloads/add_watermark/input/S_1.png",
        "/home/fl-lpt-690/Downloads/add_watermark/input/S_2.jpeg"
    ],
    "env": "PREPROD"
}

def test_add_watermark_batch_success(file_batch):
    with patch("app.add_watermark_to_files_and_zip.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "fake-task-id"
        mock_delay.return_value = mock_task

        response = client.post("/watermark/batch/", json=file_batch)
        assert response.status_code == 200
        assert response.json() == {"message": "Batch watermarking and zipping initiated.", "task_id": mock_task.id}

def test_add_watermark_batch_no_files():
    response = client.post("/watermark/batch/", json={"file_paths": [], "env": "PREPROD"})
    assert response.status_code == 400
    assert response.json() == {"detail": "No file paths provided."}

def test_get_task_status_success():
    with patch("app.AsyncResult") as mock_async:
        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_async.return_value = mock_result

        response = client.get("/status/", params={"task_id": "tid"})
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

def test_get_task_status_failure():
    with patch("app.AsyncResult") as mock_async:
        mock_result = MagicMock()
        mock_result.status = "FAILURE"
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_result.info = "Some error"
        mock_async.return_value = mock_result

        response = client.get("/status/", params={"task_id": "tid"})
        assert response.status_code == 200
        assert response.json()["status"] == "FAILURE"

def test_download_zip_file_success(tmp_path):
    fake_zip = tmp_path / "draft_files.zip"
    fake_zip.write_text("dummy zip content")

    with patch("app.AsyncResult") as mock_async:
        mock_result = MagicMock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = True
        mock_result.result = str(fake_zip)
        mock_async.return_value = mock_result

        with patch("app.cleanup_file") as mock_cleanup:
            response = client.get("/download/", params={"task_id": "tid"})
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/zip"

def test_download_zip_file_not_ready():
    with patch("app.AsyncResult") as mock_async:
        mock_result = MagicMock()
        mock_result.ready.return_value = False
        mock_async.return_value = mock_result

        response = client.get("/download/", params={"task_id": "tid"})
        assert response.status_code == 404

def test_download_zip_file_failed():
    with patch("app.AsyncResult") as mock_async:
        mock_result = MagicMock()
        mock_result.ready.return_value = True
        mock_result.successful.return_value = False
        mock_result.info = "Failed"
        mock_async.return_value = mock_result

        response = client.get("/download/", params={"task_id": "tid"})
        assert response.status_code == 500
