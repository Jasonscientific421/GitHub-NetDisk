# coding: utf-8
import logging
from types import SimpleNamespace

import app.common.signal_bus as signal_bus_module
from app.service.github_service import (
    GithubRateLimitLogHandler,
    isGithubRateLimitLogMessage,
)
from app.view.main_window import MainWindow


def test_pygithub_rate_limit_log_lines_are_detected():
    assert isGithubRateLimitLogMessage(
        'Request GET /repos/owner/repo failed with 403: rate limit exceeded')
    assert isGithubRateLimitLogMessage('Setting next backoff to 623.8s')
    assert not isGithubRateLimitLogMessage('Following Github server redirection')


def test_rate_limit_handler_emits_signal(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        signal_bus_module,
        'signalBus',
        SimpleNamespace(
            githubRateLimitSig=SimpleNamespace(
                emit=lambda message: emitted.append(message),
            ),
        ),
    )
    record = logging.LogRecord(
        'github.GithubRetry',
        logging.INFO,
        __file__,
        1,
        'Setting next backoff to %ss',
        (60,),
        None,
    )

    GithubRateLimitLogHandler().emit(record)

    assert emitted == ['Setting next backoff to 60s']


def test_rate_limit_infobar_is_throttled(monkeypatch):
    calls = []
    window = SimpleNamespace(
        _lastGithubRateLimitInfoAt=0.0,
        tr=lambda key: key,
        window=lambda: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.monotonic',
        lambda: 100.0,
    )
    monkeypatch.setattr(
        'app.view.main_window.logAction',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'app.view.main_window.InfoBar.warning',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    MainWindow.showGithubRateLimitInfo(window, 'rate limit exceeded')
    MainWindow.showGithubRateLimitInfo(window, 'Setting next backoff to 60s')

    assert len(calls) == 1
    assert calls[0][0][:2] == (
        'GitHub.RateLimit.title',
        'GitHub.RateLimit.text',
    )


