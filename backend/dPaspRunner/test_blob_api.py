"""Tests for the runner's blob endpoints, in particular the bounded fetch.

The editor asks for at most `MAX_EDITOR_LINES` lines when opening a file, and
then treats a truncated answer as read-only. That contract is what these
tests pin down: the counts have to be the file's real ones, and `content` has
to hold exactly the lines it claims to.
"""

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A test client whose blob folder is a fresh temporary directory."""
    monkeypatch.setenv("DPASP_BLOB_FOLDER", str(tmp_path) + os.sep)
    monkeypatch.setenv("MOCK", "y")  # keeps `import main` from needing dPASP
    import main

    importlib.reload(main)
    with TestClient(main.app) as test_client:
        test_client.blob_folder = str(tmp_path)
        yield test_client


def write(client, name: str, text: str) -> str:
    path = os.path.join(client.blob_folder, name)
    with open(path, "w") as handle:
        handle.write(text)
    return path


def fetch(client, name: str, **body):
    response = client.post("/blob/fetch", json={"filename": name, **body})
    assert response.status_code == 200
    return response.json()


def test_short_file_is_returned_whole(client):
    write(client, "small.pasp", "0.5::a.\n#query a.\n")
    res = fetch(client, "small.pasp", max_lines=1000)
    assert res["content"] == "0.5::a.\n#query a.\n"
    assert res["truncated"] is False
    assert res["total_lines"] == 2
    assert res["shown_lines"] == 2


def test_long_file_is_cut_at_the_limit(client):
    write(client, "big.csv", "".join(f"row{i}\n" for i in range(5000)))
    res = fetch(client, "big.csv", max_lines=1000)

    assert res["truncated"] is True
    assert res["total_lines"] == 5000
    assert res["shown_lines"] == 1000
    # Exactly the lines it claims, and no trailing newline: a phantom final
    # line would make the editor say 1001.
    assert res["content"].count("\n") == 999
    assert not res["content"].endswith("\n")
    assert res["content"].startswith("row0\n")
    assert res["content"].endswith("row999")
    assert res["bytes"] == os.path.getsize(os.path.join(client.blob_folder, "big.csv"))


def test_a_file_exactly_at_the_limit_is_not_truncated(client):
    write(client, "exact.csv", "".join(f"row{i}\n" for i in range(1000)))
    res = fetch(client, "exact.csv", max_lines=1000)

    assert res["truncated"] is False
    assert res["total_lines"] == 1000
    # Not truncated, so the file's own trailing newline is preserved: this is
    # the copy the editor may write back.
    assert res["content"].endswith("row999\n")


def test_last_line_without_a_newline_still_counts(client):
    write(client, "nonl.txt", "a\nb\nc")
    res = fetch(client, "nonl.txt", max_lines=1000)
    assert res["total_lines"] == 3
    assert res["content"] == "a\nb\nc"


def test_omitting_max_lines_returns_everything(client):
    write(client, "big.csv", "".join(f"row{i}\n" for i in range(2000)))
    res = fetch(client, "big.csv")
    assert res["truncated"] is False
    assert res["total_lines"] == 2000
    assert res["content"].count("\n") == 2000


def test_empty_file(client):
    write(client, "empty.csv", "")
    res = fetch(client, "empty.csv", max_lines=1000)
    assert res == {
        "content": "",
        "truncated": False,
        "total_lines": 0,
        "shown_lines": 0,
        "bytes": 0,
    }


def test_missing_file_reports_zero_rather_than_raising(client):
    res = fetch(client, "nope.csv", max_lines=1000)
    assert res["content"] == ""
    assert res["truncated"] is False


def test_binary_upload_does_not_break_the_endpoint(client):
    # UnicodeDecodeError is a ValueError, so it is handled like a missing
    # file rather than becoming a 500.
    path = os.path.join(client.blob_folder, "image.png")
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n\xff\xfe\x00")
    res = fetch(client, "image.png", max_lines=1000)
    assert res["content"] == ""
    assert res["truncated"] is False


def test_fetch_refuses_to_escape_the_blob_folder(client):
    res = fetch(client, "../../etc/passwd", max_lines=1000)
    assert res["content"] == ""


def test_upload_list_fetch_round_trip(client):
    assert client.post(
        "/blob/upload", json={"filename": "a.pasp", "content": "0.5::a.\n"}
    ).json() == {"status": "ok"}

    assert client.post("/blob/list", json={}).json()["files"] == ["a.pasp"]
    assert fetch(client, "a.pasp", max_lines=1000)["content"] == "0.5::a.\n"


def test_upload_refuses_to_escape_the_blob_folder(client):
    res = client.post("/blob/upload", json={"filename": "../escaped", "content": "x"})
    assert res.json()["status"] == "error"
    assert not os.path.exists(os.path.join(os.path.dirname(client.blob_folder), "escaped"))
