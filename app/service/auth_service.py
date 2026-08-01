# coding: utf-8
"""Authentication and credential storage for GitHub NetDisk.

GitHub App Device Flow is the preferred sign-in path. Personal access tokens
remain available as an explicitly selected compatibility mode. OAuth client
secrets and GitHub App private keys must never be included in this desktop
application.
"""
from dataclasses import dataclass
from threading import Event
from time import monotonic, time
from typing import Optional

import requests
from github import Auth, Github

from ..common.config import cfg
from ..common.setting import GITHUB_APP_CLIENT_ID, GITHUB_APP_SLUG


DEVICE_CODE_URL = 'https://github.com/login/device/code'
ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'
KEYRING_SERVICE = 'GitHub-NetDisk'
KEYRING_ACCOUNT = 'github-access-token'

AUTH_ANONYMOUS = 'anonymous'
AUTH_GITHUB_APP = 'github_app'
AUTH_PAT = 'pat'

LOGIN_TYPE_BY_MODE = {
    AUTH_ANONYMOUS: 'Anonymous',
    AUTH_GITHUB_APP: 'GitHubApp',
    AUTH_PAT: 'Token',
}
MODE_BY_LOGIN_TYPE = {value: key for key, value in LOGIN_TYPE_BY_MODE.items()}


class AuthError(RuntimeError):
    """Base class for authentication errors safe to display to the user."""


class AuthConfigurationError(AuthError):
    """Raised when the build does not contain a GitHub App client id."""


class DeviceFlowCancelled(AuthError):
    """Raised when the user cancels an in-progress Device Flow login."""


class CredentialStore:
    """Small wrapper around the operating-system credential vault."""

    def __init__(self):
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError:
            keyring = None
            KeyringError = Exception
        self._keyring = keyring
        self._keyring_error = KeyringError

    @property
    def available(self):
        return self._keyring is not None

    def get(self) -> str:
        if not self.available:
            return ''
        try:
            return self._keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or ''
        except self._keyring_error:
            return ''

    def set(self, token: str):
        if not self.available:
            raise AuthError('The operating-system credential store is unavailable.')
        try:
            self._keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, token)
        except self._keyring_error as error:
            raise AuthError('The operating-system credential store rejected the credential.') from error

    def delete(self):
        if not self.available:
            return
        try:
            self._keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except self._keyring_error:
            # Deleting a missing credential is equivalent to success here.
            pass


@dataclass(frozen=True)
class DeviceFlowSession:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class AuthIdentity:
    login: str
    name: str
    mode: str


@dataclass(frozen=True)
class DeviceAuthorization:
    access_token: str
    login: str
    name: str
    expires_in: int = 0


class AuthService:
    """Own the active credential and all GitHub sign-in flows."""

    def __init__(self, client_id: Optional[str] = None, store=None, http=None):
        self.clientId = GITHUB_APP_CLIENT_ID if client_id is None else str(client_id)
        self.store = store or CredentialStore()
        self.http = http or requests.Session()

    def accessToken(self) -> str:
        token = self.store.get()
        try:
            expires_at = int(cfg.get(cfg.authExpiresAt) or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if token and expires_at and time() >= expires_at:
            return ''
        return token

    def isAuthenticated(self) -> bool:
        return bool(self.accessToken())

    def mode(self) -> str:
        if not self.isAuthenticated():
            return AUTH_ANONYMOUS
        return MODE_BY_LOGIN_TYPE.get(str(cfg.get(cfg.loginType)), AUTH_PAT)

    def isGithubAppConfigured(self) -> bool:
        return bool(self.clientId.strip())

    def storeToken(self, token: str, mode: str, identity=None,
                   expires_in: int = 0) -> AuthIdentity:
        token = str(token or '').strip()
        if not token:
            raise AuthError('GitHub returned an empty access token.')
        if mode not in (AUTH_GITHUB_APP, AUTH_PAT):
            raise ValueError(f'Unsupported authentication mode: {mode}')

        if identity is None:
            user = Github(auth=Auth.Token(token)).get_user()
            identity = (user.login, user.name or user.login)
        login, name = identity
        self.store.set(token)
        cfg.set(cfg.loginType, LOGIN_TYPE_BY_MODE[mode])
        cfg.set(cfg.authExpiresAt, int(time() + expires_in) if expires_in else 0)
        cfg.set(cfg.userLoginCache, login)
        cfg.set(cfg.usernameCache, name)
        return AuthIdentity(login, name, mode)

    def disconnect(self):
        self.store.delete()
        cfg.set(cfg.loginType, LOGIN_TYPE_BY_MODE[AUTH_ANONYMOUS])
        cfg.set(cfg.authExpiresAt, 0)
        cfg.set(cfg.userLoginCache, '')
        cfg.set(cfg.usernameCache, '')

    def requestDeviceCode(self) -> DeviceFlowSession:
        if not self.isGithubAppConfigured():
            raise AuthConfigurationError(
                'GitHub App Client ID has not been configured for this build.')
        response = self.http.post(
            DEVICE_CODE_URL,
            data={'client_id': self.clientId, 'scope': 'repo'},
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        try:
            return DeviceFlowSession(
                device_code=str(data['device_code']),
                user_code=str(data['user_code']),
                verification_uri=str(data['verification_uri']),
                expires_in=max(1, int(data['expires_in'])),
                interval=max(1, int(data.get('interval') or 5)),
            )
        except (KeyError, TypeError, ValueError) as error:
            message = str(data.get('error_description') or data.get('error') or '')
            raise AuthError(message or 'GitHub returned an invalid Device Flow response.') from error

    def waitForDeviceAuthorization(self, session: DeviceFlowSession,
                                   cancel_event: Optional[Event] = None) -> DeviceAuthorization:
        cancel_event = cancel_event or Event()
        deadline = monotonic() + session.expires_in
        interval = session.interval
        while monotonic() < deadline:
            if cancel_event.wait(interval):
                raise DeviceFlowCancelled('GitHub sign-in was cancelled.')
            response = self.http.post(
                ACCESS_TOKEN_URL,
                data={
                    'client_id': self.clientId,
                    'device_code': session.device_code,
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                },
                headers={'Accept': 'application/json'},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            token = str(data.get('access_token') or '').strip()
            if token:
                user = Github(auth=Auth.Token(token)).get_user()
                return DeviceAuthorization(
                    token,
                    user.login,
                    user.name or user.login,
                    int(data.get('expires_in') or 0),
                )

            error = str(data.get('error') or '')
            if error == 'authorization_pending':
                continue
            if error == 'slow_down':
                interval += 5
                continue
            if error == 'access_denied':
                raise AuthError('GitHub authorization was denied.')
            if error == 'expired_token':
                raise AuthError('The GitHub verification code has expired.')
            message = str(data.get('error_description') or error)
            raise AuthError(message or 'GitHub Device Flow failed.')
        raise AuthError('The GitHub verification code has expired.')

    def completeDeviceAuthorization(
            self, authorization: DeviceAuthorization) -> AuthIdentity:
        return self.storeToken(
            authorization.access_token,
            AUTH_GITHUB_APP,
            (authorization.login, authorization.name),
            authorization.expires_in,
        )

    @staticmethod
    def installationUrl() -> str:
        if GITHUB_APP_SLUG.strip():
            return f'https://github.com/apps/{GITHUB_APP_SLUG.strip()}/installations/new'
        return 'https://github.com/settings/installations'


authService = AuthService()
