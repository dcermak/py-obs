import aiohttp
import dataclasses
import os
import typing
import time
import subprocess

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
    private_key_path: str | None = None

    api_url: str = "https://api.opensuse.org/"

    _session: aiohttp.ClientSession = dataclasses.field(
        default_factory=lambda: aiohttp.ClientSession()
    )

    @staticmethod
    def from_env() -> "Osc":
        if not (username := os.getenv("OSC_USER")):
            raise ValueError("environment variable OSC_USER is not set")
        if not (password := os.getenv("OSC_PASSWORD")):
            raise ValueError("environment variable OSC_PASSWORD is not set")
        return Osc(username=username, password=password)

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

    async def get_auth_header(self) -> dict[str, str]:
        assert self.private_key_path is not None
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/about") as r:
                challenge_parameters = {
                    "realm": r.headers["WWW-Authenticate"]
                    .split(",")[0]
                    .split("=")[-1]
                    .replace('"', ""),
                    "payload": r.headers["WWW-Authenticate"]
                    .split(",")[1]
                    .split("=")[-1]
                    .replace('"', ""),
                }
                CREATED_TIMESTAMP = str(int(time.time()))
                SIGNATURE_STRING = f"(created): {CREATED_TIMESTAMP}"
                cmd = [
                    "ssh-keygen",
                    "-Y",
                    "sign",
                    "-f",
                    self.private_key_path,
                    "-q",
                    "-n",
                    challenge_parameters["realm"],
                ]
                s = subprocess.run(
                    cmd, input=SIGNATURE_STRING, text=True, capture_output=True
                )

                signature = "".join(s.stdout.split("\n")[1:-2])
                auth_header = {
                    "Authorization": f'Signature keyId="{self.username}",'
                    'algorithm="ssh",'
                    f'signature="{signature}",'
                    f'headers="(created)",created="{CREATED_TIMESTAMP}"'
                }
            async with session.get(
                self.api_url, headers=auth_header, raise_for_status=True
            ) as r:
                return auth_header

    async def create_osc(self):
        if self.password is not None:
            self._session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(login=self.username, password=self.password),
                raise_for_status=True,
                base_url=self.api_url,
                # https://github.com/openSUSE/open-build-service/issues/13737
                headers={"Accept": "application/xml; charset=utf-8"},
            )
        elif self.private_key_path is not None:
            auth_header = await self.get_auth_header()
            self._session = aiohttp.ClientSession(
                raise_for_status=True,
                base_url=self.api_url,
                headers={**auth_header, "Accept": "application/xml; charset=utf-8"},
            )

    async def teardown(self) -> None:
        await self._session.close()
