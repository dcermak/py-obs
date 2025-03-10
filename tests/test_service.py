from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from py_obs.project import upload_file_contents
from py_obs.service import service_wait
from tests.conftest import HOME_PROJ_T


@pytest_asyncio.fixture(scope="function")
async def home_prj_with_service(
    home_project: HOME_PROJ_T,
) -> AsyncGenerator[HOME_PROJ_T, None]:
    osc, admin, prj, pkg = home_project
    await upload_file_contents(
        osc,
        prj,
        pkg,
        "_service",
        """<services>
    <service name="set_version" mode="disabled">
    <param name="basename">buildah</param>
    </service>
    </services>""",
    )
    yield osc, admin, prj, pkg


@pytest.mark.asyncio
async def test_service_wait(home_prj_with_service: HOME_PROJ_T) -> None:
    osc, _, prj, pkg = home_prj_with_service
    await service_wait(osc, prj, pkg)
