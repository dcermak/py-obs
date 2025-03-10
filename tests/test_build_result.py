import pytest

from py_obs.build_result import BuildResult
from py_obs.build_result import PackageCode
from py_obs.build_result import PackageStatus
from py_obs.build_result import RepositoryCode
from py_obs.build_result import fetch_build_result
from tests.conftest import OSC_FROM_ENV_T


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_pkg_build_result(osc_from_env: OSC_FROM_ENV_T) -> None:
    assert await fetch_build_result(
        osc_from_env,
        prj := "openSUSE:Factory",
        pkg := "update-test-trivial",
        repository="standard",
    ) == [
        BuildResult(
            project=prj,
            repository="standard",
            arch="x86_64",
            code=RepositoryCode.BUILDING,
            status=[
                PackageStatus(
                    package=pkg,
                    code=PackageCode.SUCCEEDED,
                    details=[],
                ),
            ],
            dirty=None,
            state=RepositoryCode.BUILDING,
        ),
        BuildResult(
            project=prj,
            repository="standard",
            arch="i586",
            code=RepositoryCode.PUBLISHED,
            status=[
                PackageStatus(
                    package=pkg,
                    code=PackageCode.EXCLUDED,
                    details=["package whitelist"],
                ),
            ],
            dirty=None,
            state=RepositoryCode.PUBLISHED,
        ),
    ]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_pkg_lastbuild_result(osc_from_env: OSC_FROM_ENV_T) -> None:
    assert await fetch_build_result(
        osc_from_env,
        prj := "openSUSE:Factory",
        pkg := "update-test-trivial",
        repository="standard",
        lastbuild=True,
    ) == [
        BuildResult(
            project=prj,
            repository="standard",
            arch="x86_64",
            code=RepositoryCode.BUILDING,
            status=[
                PackageStatus(
                    package=pkg,
                    code=PackageCode.SUCCEEDED,
                    details=[],
                ),
            ],
            dirty=None,
            state=RepositoryCode.BUILDING,
        ),
        BuildResult(
            project=prj,
            repository="standard",
            arch="i586",
            code=RepositoryCode.PUBLISHED,
            status=[
                PackageStatus(
                    package=pkg,
                    code=PackageCode.UNKNOWN,
                    details=[],
                ),
            ],
            dirty=None,
            state=RepositoryCode.PUBLISHED,
        ),
    ]
