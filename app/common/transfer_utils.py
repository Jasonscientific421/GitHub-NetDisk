# coding: utf-8
"""Helpers shared by transfer-related modules."""


def isTransferCancelledError(error):
    """Return whether ``error`` represents a user-requested cancellation."""
    message = str(error).lower()
    return (
        type(error).__name__ == '_TransferCancelled'
        or 'transfer cancelled' in message
        or 'download cancelled' in message
        or 'upload cancelled' in message
    )
