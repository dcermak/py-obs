import pytest

from py_obs.osc import Osc
from py_obs.project import fetch_meta
from tests.conftest import HOME_PROJ_T
from tests.conftest import local_obs_apiurl


@pytest.mark.asyncio
async def test_public_route(home_project: HOME_PROJ_T) -> None:
    _, _, proj, pkg = home_project
    osc = Osc(public=True, api_url=local_obs_apiurl())
    assert pkg == await fetch_meta(osc, prj=proj, pkg=pkg)
