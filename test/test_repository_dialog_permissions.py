# coding: utf-8
from types import SimpleNamespace

from app.components import dialog
from app.components.dialog import AddRepo


def test_create_repository_entry_requires_login(monkeypatch):
    monkeypatch.setattr(
        dialog.authService,
        'isAuthenticated',
        lambda: False,
    )

    assert not AddRepo.canCreateRepository()


def test_create_repository_direct_entry_is_blocked_without_login(monkeypatch):
    calls = []
    widget = SimpleNamespace(canCreateRepository=lambda: False)
    monkeypatch.setattr(
        dialog,
        'logCancelled',
        lambda action_key, *args, **kwargs: calls.append(action_key),
    )
    monkeypatch.setattr(
        dialog,
        'CreateRepo',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('CreateRepo must not be opened')),
    )

    AddRepo.onCreateRepo(widget)

    assert calls == ['Log.Action.CreateRepository']
