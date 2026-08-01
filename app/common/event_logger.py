# coding: utf-8
"""Internationalized structured event logging helpers."""
import traceback

from loguru import logger

from .translator import translate


def _log(level, template_key, action_key, detail=None):
    action = translate(action_key)
    if detail in (None, ''):
        no_detail_key = f'{template_key}.NoDetail'
        template = translate(no_detail_key)
        if template != no_detail_key:
            getattr(logger, level)(template % action)
            return
        detail = translate('Log.Event.NoDetail')
    else:
        detail = str(detail)
    getattr(logger, level)(translate(template_key, (action, detail)))


def exceptionDetail(error, context=None):
    """Return a complete traceback, including exceptions crossing threads."""
    if isinstance(error, BaseException):
        detail = ''.join(traceback.format_exception(
            type(error), error, error.__traceback__))
    else:
        detail = str(error)
    if context:
        return f'{context}\n{detail}'
    return detail


def logAction(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Action', action_key, detail)


def logStarted(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Started', action_key, detail)


def logSucceeded(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Succeeded', action_key, detail)


def logFailed(action_key, detail=None, level='error'):
    if isinstance(detail, BaseException):
        detail = exceptionDetail(detail)
    _log(level, 'Log.Event.Failed', action_key, detail)


def logCancelled(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Cancelled', action_key, detail)


def logChanged(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Changed', action_key, detail)


def logSelected(action_key, detail=None, level='debug'):
    _log(level, 'Log.Event.Selected', action_key, detail)


def logInitialized(action_key, detail=None, level='info'):
    _log(level, 'Log.Event.Initialized', action_key, detail)


def logProgress(action_key, detail=None, level='debug'):
    _log(level, 'Log.Event.Progress', action_key, detail)


def logReceived(action_key, detail=None, level='debug'):
    _log(level, 'Log.Event.Received', action_key, detail)
