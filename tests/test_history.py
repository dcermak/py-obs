import pytest

from py_obs.history import fetch_package_history
from py_obs.project import delete, upload_file_contents

from tests.conftest import HOME_PROJ_T


@pytest.mark.asyncio
async def test_history(home_project: HOME_PROJ_T) -> None:
    FNAME = "readme.txt"
    CONTENTS1 = "first version"
    CONTENTS2 = "second revision"

    async for osc, _, prj, pkg in home_project:
        hist0 = await fetch_package_history(osc, prj, pkg)
        assert len(hist0) == 0

        await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS1)
        hist1 = await fetch_package_history(osc, prj, pkg)
        assert len(hist1) == 1

        await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS2)
        hist2 = await fetch_package_history(osc, prj, pkg)
        assert len(hist2) == 2
        assert hist2[0] == hist1[0]

        assert (
            len(
                latest_entry := (
                    await fetch_package_history(osc, prj.name, pkg.name, limit=1)
                )
            )
            == 1
        )
        assert latest_entry[0] == hist2[-1]

        await delete(osc, prj=prj, pkg=pkg)

        # deleting a package results in another commit (= the deletion commit)
        assert (await fetch_package_history(osc, prj, pkg, deleted=True))[0:-1] == hist2
