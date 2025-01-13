from dataclasses import dataclass
import os
from typing import AsyncGenerator, Self
import pytest
import pytest_asyncio

from py_obs.osc import ObsException, Osc
from py_obs.person import Person
import py_obs.project as project
from py_obs.xml_factory import StrElementField


LOCAL_OSC_T = tuple[Osc, Osc]
OSC_FROM_ENV_T = Osc


def osc_test_user_name() -> str:
    return os.getenv("OSC_USER", "obsTestUser")


def local_obs_apiurl() -> str:
    return os.getenv("OBS_URL", "http://localhost:3000")


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


@dataclass(frozen=True)
class ProjectCleaner:
    """Context manager for ensuring that a specified project does not exist
    after entering and after exiting the context manager.

    """

    osc: Osc

    project: project.Project | str

    async def __aenter__(self) -> Self:
        try:
            await project.delete(self.osc, prj=self.project, force=True)
        except ObsException:
            pass

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await project.delete(self.osc, prj=self.project, force=True)
        except ObsException:
            pass
