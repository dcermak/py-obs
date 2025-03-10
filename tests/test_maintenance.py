import pytest
from aiohttp import ClientResponseError
from vcr import VCR

from py_obs.maintenance import DoubleBranchException
from py_obs.maintenance import fetch_maintained_code_streams
from py_obs.maintenance import mbranch
from tests.conftest import OSC_FROM_ENV_T
from tests.conftest import ProjectCleaner


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_fetch_maintained_code_streams_of_existing_pkg(
    osc_from_env: OSC_FROM_ENV_T,
) -> None:
    assert await fetch_maintained_code_streams(osc_from_env, "podman") == [
        "SUSE:SLE-15-SP5:Update"
    ]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_maintained_code_streams_of_invalid_pkg(
    osc_from_env: OSC_FROM_ENV_T,
) -> None:
    assert await fetch_maintained_code_streams(osc_from_env, "asdf") == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_ordinary_mbranch(osc_from_env: OSC_FROM_ENV_T, vcr: VCR) -> None:
    # run this against IBS to get a few meaningful results
    async with ProjectCleaner(
        osc_from_env,
        gcc12_maintained_prj := "home:dancermak:branches:OBS_Maintained:gcc12",
        _vcr=vcr,
    ) as _:
        assert await mbranch(osc_from_env, "gcc12") == gcc12_maintained_prj


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_mbranch_unknown_package(osc_from_env: OSC_FROM_ENV_T) -> None:
    with pytest.raises(ValueError) as val_err_ctx:
        await mbranch(osc_from_env, "passt")

    assert "Package passt cannot be maintenance branched: package not found" in str(
        val_err_ctx.value
    )
    assert isinstance(val_err_ctx.value.__cause__, ClientResponseError)


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_double_mbranch(osc_from_env: OSC_FROM_ENV_T, vcr: VCR) -> None:
    async with ProjectCleaner(
        osc_from_env,
        gcc14_maintained_prj := "home:dancermak:branches:OBS_Maintained:gcc14",
        _vcr=vcr,
    ) as _:
        # sanity check
        assert await mbranch(osc_from_env, "gcc14") == gcc14_maintained_prj

        with pytest.raises(DoubleBranchException) as dbl_branch_exc_ctx:
            await mbranch(osc_from_env, "gcc14")

        assert (
            "branch target package already exists"
            in (exc := dbl_branch_exc_ctx.value).message
        )
        assert (
            exc.package == "gcc14.SUSE_SLE-15_Update"
            and exc.project == gcc14_maintained_prj
        )
