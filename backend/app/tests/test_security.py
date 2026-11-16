from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.security import digest, passwords
from app.integrations.storage import LocalPrivateStorage, validate_content
from app.models.entities import Task, User
from app.services.tasks import owner, participant


def test_argon_passwords_are_salted_and_verified():
    a = passwords.hash("long-test-password")
    b = passwords.hash("long-test-password")
    assert a != b
    assert a.startswith("$argon2id$")
    assert passwords.verify("long-test-password", a)
    assert not passwords.verify("wrong", a)
    assert not passwords.verify("wrong", "invalid-hash")


def test_tokens_are_one_way_digests():
    assert len(digest("token")) == 64
    assert digest("token") != "token"


def test_task_ownership_rejects_unrelated_accounts():
    task = Task(owner_id="owner", assigned_worker_id="worker")
    outsider = User(id="outsider", roles=["client"])
    with pytest.raises(HTTPException) as exc:
        owner(task, outsider)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        participant(task, outsider)
    participant(task, User(id="worker", roles=["worker"]))
    participant(task, User(id="admin", roles=["admin"]))


@pytest.mark.parametrize("key", ["../secret", "C:/private", "a" * 31, "z" * 32, "a/" * 16])
def test_storage_keys_cannot_traverse_paths(key):
    storage = object.__new__(LocalPrivateStorage)
    storage.root = Path("uploads")
    with pytest.raises(HTTPException):
        storage.path(key)


def test_upload_rejects_mime_spoofing_and_excess_size():
    for content, mime in [
        (b"<script>alert(1)</script>", "image/png"),
        (b"hello", "text/html"),
        (b"a" * (5 * 1024 * 1024 + 1), "text/plain"),
        (b"\x00hidden", "text/plain"),
    ]:
        with pytest.raises(HTTPException):
            validate_content(content, mime)
    validate_content(b"Public information report.", "text/plain")
