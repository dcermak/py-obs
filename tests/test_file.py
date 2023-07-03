import asyncio
import pytest
from py_obs.project import fetch_all_files, fetch_file_contents, upload_file_contents

from tests.conftest import HOME_PROJ_T


@pytest.mark.asyncio
async def test_upload_file(home_project: HOME_PROJ_T):
    CONTENTS = "foobar"
    fname = "testfile"

    async for osc, admin_osc, prj, pkg in home_project:
        await upload_file_contents(osc, prj, pkg, fname, CONTENTS)

        for osc_ in osc, admin_osc:
            assert (
                await fetch_file_contents(osc_, prj, pkg, fname)
            ).decode() == CONTENTS


@pytest.mark.asyncio
async def test_fetch_all_files(home_project: HOME_PROJ_T):
    basename = "foo"
    contents = "bar"

    async for osc, _, prj, pkg in home_project:
        tasks = []
        for i in range(10):
            tasks.append(
                upload_file_contents(
                    osc, prj, pkg, f"{basename}-{i}", f"{contents} {i}"
                )
            )
        await asyncio.gather(*tasks)

        files = await fetch_all_files(osc, prj, pkg)

        for i in range(10):
            assert files.pop(f"{basename}-{i}").decode() == f"{contents} {i}"

        assert not files
