import pytest
from py_obs.configuration import Configuration, fetch_configuration
from tests.conftest import LOCAL_OSC_T


@pytest.mark.asyncio
async def test_configuration(local_osc: LOCAL_OSC_T) -> None:
    osc, _ = local_osc
    assert await fetch_configuration(osc) == Configuration(
        title="Open Build Service",
        name="private",
        obs_url="https://unconfigured.openbuildservice.org",
    )
