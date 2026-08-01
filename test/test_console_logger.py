# coding: utf-8
import os
import subprocess
import sys
from pathlib import Path


def _run_capture_probe(tmp_path, extra_environment=None):
    log_path = tmp_path / 'session.log'
    project_root = Path(__file__).resolve().parents[1]
    script = """
import os
from app.common.console_logger import configureLogger, installConsoleLogCapture

capture = installConsoleLogCapture(r'{log_path}')
logger = configureLogger(capture, r'{log_path}')
print('python-stdout-line')
os.write(2, b'native-stderr-line\\n')
logger.info('loguru-line')
logger.remove()
capture.close()
""".format(log_path=log_path)
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, (
        str(project_root),
        environment.get('PYTHONPATH', ''),
    )))
    environment.update(extra_environment or {})

    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return result, log_path.read_text(encoding='utf-8')


def test_stdout_stderr_and_loguru_share_one_session_log(tmp_path):
    result, content = _run_capture_probe(tmp_path)

    assert 'python-stdout-line' in result.stdout
    assert 'native-stderr-line' in result.stderr
    assert 'loguru-line' in result.stderr
    assert 'python-stdout-line' in content
    # Windows defaults to stream capture to avoid CPython stderr finalization
    # failures, so raw os.write() output is only guaranteed in fd mode.
    assert content.count('loguru-line') == 1


def test_fd_capture_mode_records_native_stderr(tmp_path):
    result, content = _run_capture_probe(
        tmp_path,
        {'GITHUB_NETDISK_FD_CAPTURE': '1'},
    )

    assert 'native-stderr-line' in result.stderr
    assert 'native-stderr-line' in content
    assert content.count('loguru-line') == 1


def test_missing_stdout_and_stderr_are_still_captured(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, (
        str(project_root),
        environment.get('PYTHONPATH', ''),
    )))

    for mode in ('stream', 'fd'):
        log_path = tmp_path / f'{mode}.log'
        script = """
import sys
from app.common.console_logger import ConsoleLogCapture, configureLogger

sys.stdout = None
sys.stderr = None
capture = ConsoleLogCapture(r'{log_path}', mode='{mode}')
logger = configureLogger(capture, r'{log_path}')
print('python-without-console')
logger.info('loguru-without-console')
from PyQt5.QtCore import qWarning
qWarning('qt-without-console')
logger.remove()
capture.close()
""".format(log_path=log_path, mode=mode)

        subprocess.run(
            [sys.executable, '-c', script],
            cwd=project_root,
            env=environment,
            capture_output=True,
            check=True,
        )
        content = log_path.read_text(encoding='utf-8')
        assert content.count('python-without-console') == 1
        assert content.count('loguru-without-console') == 1
        assert content.count('qt-without-console') == 1
