# coding: utf-8
"""Tee Python and native-process console output into the session log."""
import os
import sys
import atexit
from pathlib import Path
from threading import Lock, Thread


class TeeStream:
    """Mirror Python stream writes to the original stream and the log file."""

    def __init__(self, stream, write_log):
        self._stream = stream
        self._write_log = write_log
        self.encoding = getattr(stream, 'encoding', None)
        self.errors = getattr(stream, 'errors', None)

    def write(self, text):
        text = str(text)
        write = getattr(self._stream, 'write', None)
        written = write(text) if callable(write) else len(text)
        self._write_log(text.encode(
            self.encoding or 'utf-8',
            errors=self.errors or 'backslashreplace',
        ))
        return len(text) if written is None else written

    def flush(self):
        flush = getattr(self._stream, 'flush', None)
        return flush() if callable(flush) else None

    def isatty(self):
        isatty = getattr(self._stream, 'isatty', None)
        return bool(isatty()) if callable(isatty) else False

    def fileno(self):
        fileno = getattr(self._stream, 'fileno', None)
        if not callable(fileno):
            raise OSError('The application has no console file descriptor.')
        return fileno()

    def reconfigure(self, *args, **kwargs):
        if hasattr(self._stream, 'reconfigure'):
            return self._stream.reconfigure(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._stream, name)


class ConsoleLogCapture:
    """Capture file descriptors 1 and 2 without hiding terminal output."""

    def __init__(self, log_path, mode='auto'):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fd = os.open(
            self.log_path,
            os.O_CREAT | os.O_WRONLY | os.O_APPEND,
            0o644,
        )
        self._log_lock = Lock()
        self._redirects = []
        self._closed = False
        self.console_is_tty = False
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._wrapped_streams = []
        self._previous_qt_handler = None
        self._qt_handler_installed = False
        self._mode = self._resolve_mode(mode)
        if self._mode == 'fd':
            for fd in (1, 2):
                self._redirect(fd)
            self._redirect_missing_streams()
            if not any(fd == 2 for fd, _, _ in self._redirects):
                self._install_qt_message_handler()
        else:
            self._redirect_streams()
            self._install_qt_message_handler()
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(line_buffering=True)
            except (AttributeError, OSError):
                pass

    @staticmethod
    def _resolve_mode(mode):
        if mode in ('fd', 'stream'):
            return mode
        if sys.platform == 'win32' and os.environ.get('GITHUB_NETDISK_FD_CAPTURE') != '1':
            return 'stream'
        return 'fd'

    @staticmethod
    def _write_all(fd, data):
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]

    def _write_log(self, data):
        with self._log_lock:
            try:
                self._write_all(self._log_fd, data)
            except OSError:
                pass

    def _redirect_streams(self):
        self.console_is_tty = bool(getattr(sys.stderr, 'isatty', lambda: False)())
        self._wrap_stream('stdout')
        self._wrap_stream('stderr')

    def _redirect_missing_streams(self):
        for name in ('stdout', 'stderr'):
            if getattr(sys, name) is None:
                self._wrap_stream(name)

    def _wrap_stream(self, name):
        original = getattr(sys, name)
        setattr(sys, name, TeeStream(original, self._write_log))
        self._wrapped_streams.append((name, original))

    def _install_qt_message_handler(self):
        try:
            from PyQt5.QtCore import qInstallMessageHandler
        except Exception:
            return

        def handler(mode, context, message):
            line = f'Qt[{int(mode)}] {message}\n'
            self._write_log(line.encode('utf-8', errors='backslashreplace'))
            if self._previous_qt_handler:
                self._previous_qt_handler(mode, context, message)
            else:
                try:
                    self._original_stderr.write(line)
                    self._original_stderr.flush()
                except Exception:
                    pass

        self._previous_qt_handler = qInstallMessageHandler(handler)
        self._qt_handler_installed = True

    def _redirect(self, fd):
        try:
            original_fd = os.dup(fd)
            read_fd, write_fd = os.pipe()
            is_tty = os.isatty(original_fd)
            os.dup2(write_fd, fd)
            os.close(write_fd)
        except OSError:
            return

        thread = Thread(
            target=self._pump,
            args=(read_fd, original_fd),
            name=f'console-log-{fd}',
            daemon=True,
        )
        self._redirects.append((fd, original_fd, thread))
        thread.start()
        if fd == 2:
            self.console_is_tty = is_tty

    def _pump(self, read_fd, original_fd):
        try:
            while True:
                data = os.read(read_fd, 8192)
                if not data:
                    break
                try:
                    self._write_all(original_fd, data)
                except OSError:
                    pass
                self._write_log(data)
        finally:
            os.close(read_fd)

    def close(self):
        if self._closed:
            return
        self._closed = True
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        if self._qt_handler_installed:
            try:
                from PyQt5.QtCore import qInstallMessageHandler
                qInstallMessageHandler(self._previous_qt_handler)
            except Exception:
                pass
        if self._mode == 'fd':
            for fd, original_fd, _thread in self._redirects:
                try:
                    os.dup2(original_fd, fd)
                except OSError:
                    pass
            for _fd, _original_fd, thread in self._redirects:
                thread.join(timeout=2)
            for _fd, original_fd, _thread in self._redirects:
                try:
                    os.close(original_fd)
                except OSError:
                    pass
        for name, original in self._wrapped_streams:
            setattr(sys, name, original)
        try:
            os.close(self._log_fd)
        except OSError:
            pass


def installConsoleLogCapture(log_path):
    if os.environ.get('GITHUB_NETDISK_NO_CONSOLE_CAPTURE') == '1':
        return None
    capture = ConsoleLogCapture(log_path)
    atexit.register(capture.close)
    return capture


def configureLogger(capture, log_path):
    """Route Loguru separately to console and file to avoid duplicate logs."""
    from loguru import logger

    logger.remove()
    console_is_tty = getattr(capture, 'console_is_tty', None)
    if console_is_tty is None:
        try:
            console_is_tty = sys.stderr.isatty()
        except Exception:
            console_is_tty = False
    console_stream = sys.stderr
    has_console_stream = callable(getattr(console_stream, 'write', None))
    if has_console_stream:
        logger.add(
            console_stream,
            colorize=console_is_tty,
            catch=True,
        )
    if capture is None or not has_console_stream:
        logger.add(
            str(Path(log_path).absolute()),
            colorize=False,
            encoding='utf-8',
            catch=True,
        )
    return logger
