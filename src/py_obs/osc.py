import dataclasses
import http.cookiejar
import os
import re
import subprocess
import time
import typing
import urllib.request

import aiohttp
from multidict import CIMultiDictProxy
from yarl import URL

from py_obs.logger import LOGGER


class ObsException(aiohttp.ClientResponseError):
    def __str__(self) -> str:
        return (
            f"Error talking to OBS: {self.status=}, {self.message=},"
            f"{self.request_info=}"
        )


class SignatureAuth(aiohttp.BasicAuth):
    def __new__(
        cls, login: str, ssh_key_path: str, response_headers
    ) -> "SignatureAuth":
        # TODO: add type hint for response_headers
        self = super().__new__(cls, login)
        self.ssh_key_path = ssh_key_path  # type: ignore[attr-defined]
        self.response_headers = response_headers  # type: ignore[attr-defined]
        return self  # type: ignore[return-value]

    def encode(self) -> str:
        if not os.path.isfile(self.ssh_key_path):  # type: ignore[attr-defined]
            raise RuntimeError(
                "The specified SSH key file does not exist: "
                + self.ssh_key_path  # type: ignore[attr-defined]
            )

        challenge = self.response_headers.get(  # type: ignore[attr-defined]
            "WWW-Authenticate"
        ).split(" ", 1)[1]
        parsed_challenge = urllib.request.parse_keqv_list(
            urllib.request.parse_http_list(challenge)
        )
        realm = parsed_challenge["realm"]
        now = int(time.time())
        data = f"(created): {now}"
        cmd = [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            self.ssh_key_path,  # type: ignore[attr-defined]
            "-n",
            realm,
            "-q",
        ]
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8"
        )
        stdout, _ = proc.communicate(data)

        match = re.match(
            r"\A-----BEGIN SSH SIGNATURE-----\n(.*)\n-----END SSH SIGNATURE-----",
            stdout,
            re.S,
        )
        if not match:
            raise RuntimeError("Could not extract SSH signature")

        # headers must not contain newlines; removing them makes no difference
        # in base64 encoded text
        sig = match.group(1).replace("\n", "")

        auth = (
            f'Signature keyId="{self.login}",algorithm="ssh",headers="(created)",'
            f'created={now},signature="{sig}"'
        )
        return auth


class CookieJar(http.cookiejar.LWPCookieJar):
    """
    A wrapper encapsulating LWPCookieJar for use in aiohttp.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if os.path.isfile(self.filename):
            try:
                self.load()
            except http.cookiejar.LoadError:
                pass

    def filter_cookies(self, request_url):
        result = []
        for cookie in self:
            if cookie.domain == request_url.host or (
                cookie.domain.startswith(".")
                and request_url.host.endswith(cookie.domain)
            ):
                result.append((cookie.name, cookie.value))
        return result

    def update_cookies(self, cookies, response_url):
        for name, cookie in cookies.items():
            if cookie["max-age"]:
                now = int(time.time())
                expires = now + int(cookie["max-age"])
            elif cookie["expires"]:
                expires = cookie["expires"]
            else:
                expires = None

            c = http.cookiejar.Cookie(
                version=cookie["version"] or 0,
                name=name,
                value=cookie.value,
                port=None,
                port_specified=False,
                domain=cookie["domain"] or None,
                domain_specified=True,
                domain_initial_dot=cookie["domain"].startswith("."),
                path=cookie["path"] or None,
                path_specified=True,
                secure=cookie["secure"] or None,
                expires=expires,
                discard=False,
                comment=cookie["comment"] or None,
                comment_url=None,
                rest={},
            )
            self.set_cookie(c)

        try:
            os.makedirs(os.path.dirname(self.filename), mode=0o700)
        except FileExistsError:
            pass

        self.save()


_DEFAULT_API_URL = "https://api.opensuse.org/"


@dataclasses.dataclass
class Osc:
    username: str
    password: str = ""
    api_url: str = _DEFAULT_API_URL
    ssh_key_path: str | None = None
    cookie_jar_path: str = os.path.expanduser("~/.local/state/osc/cookiejar")

    _session: aiohttp.ClientSession = dataclasses.field(
        default_factory=lambda: aiohttp.ClientSession()
    )
    _default_headers: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            # https://github.com/openSUSE/open-build-service/issues/13737
            "Accept": "application/xml; charset=utf-8",
        }
    )

    @staticmethod
    def from_env() -> "Osc":
        if not (username := os.getenv("OSC_USER")):
            raise ValueError("environment variable OSC_USER is not set")
        return Osc(
            username=username,
            password=os.getenv("OSC_PASSWORD", ""),
            ssh_key_path=os.getenv("OSC_SSH_PUBKEY"),
            api_url=os.getenv("OSC_APIURL", _DEFAULT_API_URL),
        )

    async def api_request(
        self,
        route: str,
        payload: bytes | str | None = None,
        params: dict[str, str] | None = None,
        method: typing.Literal["GET", "POST", "PUT", "DELETE"] = "GET",
    ) -> aiohttp.ClientResponse:
        LOGGER.debug(
            "Sending a %s request to %s with the parameters %s and the payload %s",
            method,
            route,
            params,
            payload,
        )

        headers = list(self._default_headers.items())
        for cookie in self._session.cookie_jar.filter_cookies(URL(self.api_url)):
            headers.append(cookie)  # type: ignore[arg-type]

        try:
            return await self._session.request(
                method=method,
                params=params,
                url=route,
                data=payload,
                headers=headers,
            )
        except aiohttp.ClientResponseError as cre_exc:
            if cre_exc.status != 401:
                raise ObsException(**cre_exc.__dict__) from cre_exc

            # TODO: lock and run the following code only in 1 thread; other
            # threads should use session cookies again

            # needed to make mypy happy, in theory cre_exc.headers can have a
            # different type as well…
            assert isinstance(cre_exc.headers, CIMultiDictProxy)
            supported_auth_methods = [
                i.split(" ")[0].lower()
                for i in (cre_exc.headers).getall("WWW-Authenticate")
            ]
            LOGGER.debug(f"Supported auth methods: {supported_auth_methods}")

            auth: SignatureAuth | aiohttp.BasicAuth | None = None
            for auth_method in supported_auth_methods:
                if auth_method == "signature" and self.ssh_key_path:
                    auth = SignatureAuth(
                        login=self.username,
                        ssh_key_path=self.ssh_key_path,
                        response_headers=cre_exc.headers,
                    )
                    break
                elif auth_method == "basic" and self.password:
                    auth = aiohttp.BasicAuth(
                        login=self.username, password=self.password
                    )
                    break

            if not auth:
                # we have no suitable auth handler, let's re-raise the original
                # exception
                raise ObsException(**cre_exc.__dict__) from cre_exc

            return await self._session.request(
                method=method, params=params, url=route, data=payload, auth=auth
            )

    def __post_init__(self) -> None:
        if not self.password and not self.ssh_key_path:
            raise ValueError(
                "Either a password or a path to the ssh public key must be provided"
            )
        self._session = aiohttp.ClientSession(
            raise_for_status=True,
            base_url=self.api_url,
            headers=self._default_headers,
            cookie_jar=CookieJar(self.cookie_jar_path),  # type: ignore[arg-type]
        )

    async def teardown(self) -> None:
        await self._session.close()
