# coding: utf-8
from app.common import event_logger


def test_no_detail_event_uses_natural_sentence(monkeypatch):
    messages = []
    translations = {
        'Log.Action.Quit': '退出应用程序',
        'Log.Event.Action.NoDetail': '用户触发操作：%s',
        'Log.Event.NoDetail': '无附加信息',
        'Log.Event.Action': '用户触发操作：%s（%s）',
    }
    monkeypatch.setattr(
        event_logger,
        'translate',
        lambda key, args=(): translations.get(key, key) % args if args else translations.get(key, key),
    )
    monkeypatch.setattr(
        event_logger.logger,
        'info',
        lambda message: messages.append(message),
    )

    event_logger.logAction('Log.Action.Quit')

    assert messages == ['用户触发操作：退出应用程序']
