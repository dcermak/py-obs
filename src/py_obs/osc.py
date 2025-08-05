import asyncio
import configparser
import dataclasses
import http.cookiejar
from http.cookies import BaseCookie
import os
import os.path
import re
import subprocess
import time
import typing
import urllib.request

import aiohttp
from aiohttp.abc import AbstractCookieJar, ClearCookiePredicate
from aiohttp.typedefs import LooseCookies
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
                "The specified SSH key file does not exist: " + self.ssh_key_path  # type: ignore[attr-defined]
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
        stdout, stderr = proc.communicate(data)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ssh-keygen exited with {proc.returncode} and got {stdout=}, {stderr=}"
            )

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


class CookieJar(AbstractCookieJar):
    """A wrapper that creates aiohttp.CookieJar with LWP file persistence"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._jar: aiohttp.CookieJar | None = None

    def _ensure_jar(self) -> aiohttp.CookieJar:
        if self._jar is None:
            self._jar = aiohttp.CookieJar()
            self._load_from_lwp()
        return self._jar

    def _load_from_lwp(self) -> None:
        if os.path.isfile(self.file_path):
            lwp_jar = http.cookiejar.LWPCookieJar(self.file_path)
            try:
                lwp_jar.load(ignore_discard=True, ignore_expires=True)
                # Convert LWP cookies to aiohttp format
                for cookie in lwp_jar:
                    if self._jar is not None:
                        self._jar.update_cookies({cookie.name: cookie.value or ""})
            except http.cookiejar.LoadError:
                pass

    def _save_to_lwp(self) -> None:
        if self._jar is None:
            return

        lwp_jar = http.cookiejar.LWPCookieJar(self.file_path)

        # Convert aiohttp cookies back to LWP format
        for cookie in self._jar:
            # Handle expires time
            expires = None
            if cookie.get("expires"):
                expires_val = cookie["expires"]
                if hasattr(expires_val, "timestamp"):
                    expires = int(expires_val.timestamp())
                else:
                    expires = expires_val

            domain = cookie.get("domain", "")
            lwp_cookie = http.cookiejar.Cookie(
                version=0,
                name=cookie.key,
                value=cookie.value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path=cookie.get("path", "/"),
                path_specified=True,
                secure=cookie.get("secure", False),
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
            )
            lwp_jar.set_cookie(lwp_cookie)

        os.makedirs(os.path.dirname(self.file_path), mode=0o700, exist_ok=True)
        lwp_jar.save(ignore_discard=True, ignore_expires=True)

    def update_cookies(
        self, cookies: LooseCookies, response_url: URL | None = None
    ) -> None:
        jar = self._ensure_jar()
        jar.update_cookies(cookies, response_url or URL())
        self._save_to_lwp()

    def filter_cookies(self, request_url: URL) -> BaseCookie[str]:
        return self._ensure_jar().filter_cookies(request_url)

    def __iter__(self):
        return iter(self._ensure_jar())

    def __len__(self) -> int:
        return len(self._ensure_jar())

    def clear(self, predicate: ClearCookiePredicate | None = None) -> None:
        return self._ensure_jar().clear(predicate)

    def clear_domain(self, domain: str) -> None:
        self._ensure_jar().clear_domain(domain)

    @property
    def quote_cookie(self) -> bool:
        return self._ensure_jar().quote_cookie


_DEFAULT_API_URL = "https://api.opensuse.org/"


@dataclasses.dataclass(frozen=True)
class BackOff:
    """Settings for the exponential backoff in :py:func:`Osc.api_request`."""

    #: total number of retries before giving up
    retries: int = 5

    #: initial sleep time in seconds after the first failure
    initial_sleep_time: float = 1.0

    #: exponential growth factor between consecutive failures
    increase_factor: float = 2.0


@dataclasses.dataclass
class Osc:
    username: str = ""
    password: str = ""
    api_url: str = _DEFAULT_API_URL
    ssh_key_path: str | None = None

    #: Use the undocumented public/ routes used for interconnect to communicate
    #: with OBS
    #: This allows you to talk to OBS without authentication, but only a subset
    #: of the API routes is present. Use at your own risk.
    public: bool = False
    cookie_jar_path: str = os.path.expanduser("~/.local/state/osc/cookiejar")

    _cookie_jar: CookieJar = None  # type: ignore[assignment]
    _auth: aiohttp.BasicAuth | SignatureAuth | None = None

    _default_headers: dict[str, str] = dataclasses.field(
        default_factory=lambda: {
            # https://github.com/openSUSE/open-build-service/issues/13737
            "Accept": "application/xml; charset=utf-8",
        }
    )

    #: status codes on which we retry a request
    _RETRY_STATUSES: typing.ClassVar[tuple[int, ...]] = (500, 502, 503, 504)

    @staticmethod
    def from_oscrc(api_url: str | None = None) -> "Osc":
        """Create a Osc instance from the oscrc config file."""
        with open(
            os.path.join(
                os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                "osc",
                "oscrc",
            ),
            "r",
            encoding="utf-8",
        ) as oscrc_f:
            oscrc = configparser.ConfigParser(default_section="general")
            oscrc.read_file(oscrc_f)

        if not api_url:
            try:
                api_url = oscrc["general"]["apiurl"]
            except KeyError:
                raise ValueError("oscrc general section is missing the apiurl option")

        try:
            sect = oscrc[api_url]
        except KeyError:
            raise ValueError(f"Missing section '{api_url}' in oscrc")

        try:
            user = sect["user"]
        except KeyError:
            raise ValueError(f"user option missing in section '{api_url}'")

        if "pass" in sect:
            return Osc(password=sect["pass"], username=user, api_url=api_url)
        if "sshkey" in sect:
            return Osc(
                ssh_key_path=os.path.expanduser(f"~/.ssh/{sect['sshkey']}.pub"),
                username=user,
                api_url=api_url,
            )

        raise ValueError(f"pass and sshkey are both missing in section '{api_url}'")

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
        params: typing.Mapping[str, str | list[str]] | None = None,
        method: typing.Literal["GET", "POST", "PUT", "DELETE"] = "GET",
        backoff: BackOff | None = None,
        raise_for_status: bool = True,
    ) -> aiohttp.ClientResponse:
        """Perform a API request against the configured build service instance
        using the supplied route.

        This function is a wrapper around aiohttp's ``session.request`` but
        performs the following additional steps:

        - retry requests that receive an error 500, 502, 503 or 504 with an
          exponentially increasing wait time in between (the status codes
          defined in :py:attr:`~Osc._RETRY_STATUSES`) using the supplied
          `backoff` parameter for the exponential backoff

        - authenticate with the IBS ssh auth

        - optionally prepend ``/public/`` to the route if the
          :py:attr:`~Osc.public` flag is set

        """
        if self.public:
            route = f"/public{route}"

        LOGGER.debug(
            "Sending a %s request to %s with the parameters %s and the payload %s",
            method,
            route,
            params,
            payload,
        )

        assert self._cookie_jar is not None, (
            "_cookie_jar must have been created in __post_init__"
        )

        backoff = backoff or BackOff()

        async with aiohttp.ClientSession(
            raise_for_status=raise_for_status,
            base_url=self.api_url,
            headers=self._default_headers,
            cookie_jar=typing.cast(AbstractCookieJar, self._cookie_jar),
        ) as session:
            headers = list(self._default_headers.items())
            for cookie in session.cookie_jar.filter_cookies(URL(self.api_url)):
                headers.append(cookie)  # type: ignore[arg-type]

            try:
                sleep_time = backoff.initial_sleep_time
                resp: None | aiohttp.ClientResponse = None

                for i in range(backoff.retries):
                    try:
                        resp = await session.request(
                            method=method,
                            params=params,
                            url=route,
                            data=payload,
                            headers=headers,
                            auth=self._auth,
                        )
                        if resp.status not in Osc._RETRY_STATUSES:
                            return resp
                    except asyncio.TimeoutError:
                        pass

                    # don't wait after the last try
                    if i == backoff.retries - 1:
                        break

                    await asyncio.sleep(sleep_time)
                    sleep_time *= backoff.increase_factor

                if resp is None:
                    raise RuntimeError(
                        f"Sending a {method} request to {route} timed out"
                    )

                resp.raise_for_status()
                assert False, "This code path must be unreachable"

            except aiohttp.ClientResponseError as cre_exc:
                if cre_exc.status != 401:
                    raise ObsException(**cre_exc.__dict__) from cre_exc

                if cre_exc.status == 401 and self.public:
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

                for auth_method in supported_auth_methods:
                    if auth_method == "signature" and self.ssh_key_path:
                        self._auth = SignatureAuth(
                            login=self.username,
                            ssh_key_path=self.ssh_key_path,
                            response_headers=cre_exc.headers,
                        )
                        break
                    elif auth_method == "basic" and self.password:
                        self._auth = aiohttp.BasicAuth(
                            login=self.username, password=self.password
                        )
                        break

                if not self._auth:
                    # we have no suitable auth handler, let's re-raise the original
                    # exception
                    raise ObsException(**cre_exc.__dict__) from cre_exc

                return await session.request(
                    method=method,
                    params=params,
                    url=route,
                    data=payload,
                    auth=self._auth,
                )

    @staticmethod
    async def _raise_for_status(resp: aiohttp.ClientResponse) -> None:
        # mimic osc's behavior here
        # https://github.com/openSUSE/osc/blob/110ddafbc0b1df235ea403b1ce3f6ab17cacc844/osc/connection.py#L236
        if resp.status > 400 and resp.status not in Osc._RETRY_STATUSES:
            resp.raise_for_status()

    def __post_init__(self) -> None:
        if not self.username and not self.public:
            raise ValueError(
                "A username must be provided if the public route is not used"
            )

        if (not self.password and not self.ssh_key_path) and not self.public:
            raise ValueError(
                "Either a password or a path to the ssh public key must be provided"
            )
        if self.password:
            self._auth = aiohttp.BasicAuth(login=self.username, password=self.password)

        self._cookie_jar = CookieJar(self.cookie_jar_path)
