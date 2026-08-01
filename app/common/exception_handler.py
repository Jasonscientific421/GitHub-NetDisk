# coding: utf-8
import traceback
from copy import deepcopy
from loguru import logger
from .setting import DEBUG
from .translator import translate


def exceptionHandler(*default):
    """ decorator for exception handling

    Parameters
    ----------
    *default:
        the default value returned when an exception occurs
    """

    def outer(func):

        def inner(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BaseException as e:
                if DEBUG:
                    logger.error(translate(
                        'Log.Event.Failed',
                        (translate('Log.Action.Application'), traceback.format_exc()),
                    ))

                value = deepcopy(default)
                if len(value) == 0:
                    return None
                elif len(value) == 1:
                    return value[0]

                return value

        return inner

    return outer
