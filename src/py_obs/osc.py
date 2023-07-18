import aiohttp
import dataclasses
import os
import re
import subprocess
import time
import typing

from py_obs.logger import LOGGER


class ObsException(aiohttp.ClientResponseError):
    def __str__(self) -> str:
        return (
            f"Error talking to OBS: {self.status=}, {self.message=},"
            f"{self.request_info=}"
        )


@dataclasses.dataclass
class Osc:
    username: str
    password: str | None = None
    ssh_public_key: str | None = None

    api_url: str = "https://api.opensuse.org/"

    _session: aiohttp.ClientSession = dataclasses.field(
        default_factory=lambda: aiohttp.ClientSession()
    )

    @staticmethod
    def from_env() -> "Osc":
        if not (username := os.getenv("OSC_USER")):
            raise ValueError("environment variable OSC_USER is not set")
        ssh_public_key = None
        if not (password := os.getenv("OSC_PASSWORD")) and not (
            ssh_public_key := os.getenv("OSC_SSH_PUBKEY")
        ):
            raise ValueError(
                "environment variable OSC_PASSWORD or OSC_SSH_PUBKEY is not set"
            )
        return Osc(username=username, password=password, ssh_public_key=ssh_public_key)

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
        try:
            return await self._session.request(
                method=method, params=params, url=route, data=payload
            )
        except aiohttp.ClientResponseError as cre_exc:
            raise ObsException(**cre_exc.__dict__) from cre_exc

    def __post_init__(self) -> None:
        # https://github.com/openSUSE/open-build-service/issues/13737
        headers = {"Accept": "application/xml; charset=utf-8"}
        auth = None

        if self.password:
            auth = aiohttp.BasicAuth(login=self.username, password=self.password)

        elif self.ssh_public_key:
            realm = "Use your developer account"
            # Signature realm="Use your developer account",headers="(created)"

            now = int(time.time())
            data = f"(created): {now}"
            cmd = [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                self.ssh_public_key,
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
            if not match or not match.group(1):
                raise ValueError(f"ssh-keygen output did not match: {stdout}")

            # headers must not contain newlines; removing them makes no
            # difference in base64 encoded text
            sig = match.group(1).replace("\n", "")

            headers["Authorization"] = (
                f'Signature keyId="{self.username}",algorithm="ssh",'
                f'headers="(created)",created={now},signature="{sig}"'
            )

        else:
            raise ValueError("password or ssh_public_key parameters must be provided")

        self._session = aiohttp.ClientSession(
            auth=auth,
            raise_for_status=True,
            base_url=self.api_url,
            headers=headers,
        )

    async def teardown(self) -> None:
        await self._session.close()
