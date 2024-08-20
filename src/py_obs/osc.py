import asyncio
import configparser
import dataclasses
import http.cookiejar
import os
import os.path
import re
import subprocess
import time
import typing
import urllib.request

import aiohttp
from aiohttp.abc import AbstractCookieJar
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

        assert (
            self._cookie_jar is not None
        ), "_cookie_jar must have been created in __post_init__"

        backoff = backoff or BackOff()

        async with aiohttp.ClientSession(
            raise_for_status=True,
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
