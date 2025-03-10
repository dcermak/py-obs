import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Self
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from vcr import VCR
from vcr.record_mode import RecordMode

import py_obs.project as project
from py_obs.osc import ObsException
from py_obs.osc import Osc
from py_obs.person import Person
from py_obs.xml_factory import StrElementField

LOCAL_OSC_T = tuple[Osc, Osc]
OSC_FROM_ENV_T = Osc


@pytest.fixture(scope="module")
def vcr_config():
    return {"filter_headers": ["authorization", "openSUSE_session"]}


def osc_test_user_name() -> str:
    return os.getenv("OSC_USER", "obsTestUser")


def local_obs_apiurl() -> str:
    url = os.getenv("OBS_URL", "http://localhost:3000")
    if (u := urlparse(url)).hostname != "localhost" and u.scheme != "https":
        raise ValueError("Cannot use non HTTPS on non localhost")
    return url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def osc_from_env() -> AsyncGenerator[OSC_FROM_ENV_T, None]:
    ssh_key_path = os.getenv("OSC_SSH_PUBKEY")
    yield Osc(
        username=osc_test_user_name(),
        password=os.getenv(
            "OSC_PASSWORD", "surely-invalid" if not ssh_key_path else ""
        ),
        api_url=local_obs_apiurl(),
        ssh_key_path=ssh_key_path,
    )


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def local_osc(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[LOCAL_OSC_T, None]:
    request.applymarker(pytest.mark.local_obs)
    local = Osc(
        username=osc_test_user_name(),
        password=os.getenv("OSC_PASSWORD", "nots3cr3t"),
        api_url=(api_url := local_obs_apiurl()),
    )
    admin = Osc(username="Admin", password="opensuse", api_url=api_url)
    yield (local, admin)


HOME_PROJ_T = tuple[Osc, Osc, project.Project, project.Package]


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def home_project(local_osc: LOCAL_OSC_T) -> AsyncGenerator[HOME_PROJ_T, None]:
    osc, admin = local_osc
    prj = project.Project(
        name=f"home:{osc.username}",
        title=StrElementField("my home project"),
        person=[Person(userid=osc.username)],
    )
    pkg = project.Package(name="emacs", title=StrElementField("The Emacs package"))

    # try to delete the home project in case it is left over from previous
    # unsuccessful test runs
    async with ProjectCleaner(osc, prj) as _:
        await project.send_meta(osc, prj=prj)
        await project.send_meta(osc, prj=prj, pkg=pkg)

        yield osc, admin, prj, pkg


@dataclass
class ProjectCleaner:
    """Context manager for ensuring that a specified project does not exist
    after entering and after exiting the context manager.

    You can optionally specify a ``VCR`` instance from the ``vcr`` fixture. This
    class will then perform no requests if vcr is not recording. This prevents
    weird glitches when matching DELETE requests against recorded ones.

    """

    osc: Osc

    project: project.Project | str

    _vcr: VCR | None = None

    _recording: bool = True

    def __post_init__(self) -> None:
        if self._vcr is not None:
            self._recording = self._vcr.record_mode != RecordMode.NONE

    async def __aenter__(self) -> Self:
        if self._recording:
            try:
                await project.delete(self.osc, prj=self.project, force=True)
            except ObsException:
                pass

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._recording:
            try:
                await project.delete(self.osc, prj=self.project, force=True)
            except ObsException:
                pass
