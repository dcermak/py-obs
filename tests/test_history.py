import re
from datetime import datetime

import pytest

from py_obs.history import fetch_package_history
from py_obs.project import delete
from py_obs.project import fetch_package_diff
from py_obs.project import upload_file_contents
from tests.conftest import HOME_PROJ_T


@pytest.mark.asyncio
async def test_history(home_project: HOME_PROJ_T) -> None:
    FNAME = "readme.txt"
    CONTENTS1 = "first version"
    CONTENTS2 = "second revision"

    osc, _, prj, pkg = home_project

    start = datetime.now()
    # obs does not write microseconds into the commit timestamps anymore
    start = start.replace(microsecond=0)

    hist0 = await fetch_package_history(osc, prj, pkg)
    assert len(hist0) == 0

    await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS1)
    hist1 = await fetch_package_history(osc, prj, pkg)
    assert len(hist1) == 1
    assert hist1[0].time >= start
    assert hist1[0].time < datetime.now()

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


@pytest.mark.asyncio
async def test_diff(home_project: HOME_PROJ_T) -> None:
    FNAME = "readme.txt"
    CONTENTS1 = "first version"
    CONTENTS2 = "second revision"

    osc, _, prj, pkg = home_project

    await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS1)
    first_diff = await fetch_package_diff(osc, prj, pkg)
    assert re.search(rf"^\+{CONTENTS1}$", first_diff, re.MULTILINE)

    await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS1 + "\n" + CONTENTS2)
    second_diff = await fetch_package_diff(osc, prj, pkg)
    assert re.search(rf"^\+{CONTENTS2}$", second_diff, re.MULTILINE)

    await upload_file_contents(osc, prj, pkg, FNAME, CONTENTS2)
    third_diff = await fetch_package_diff(osc, prj, pkg)
    assert re.search(rf"^-{CONTENTS1}", third_diff, re.MULTILINE)

    await upload_file_contents(
        osc,
        prj,
        pkg,
        (other_file := "don-t-readme.txt"),
        "\n".join((FNAME, CONTENTS1, CONTENTS2)),
    )
    assert not await fetch_package_diff(osc, prj, pkg, limit_to_files=[FNAME])
    assert await fetch_package_diff(osc, prj, pkg, limit_to_files=[other_file])

    assert first_diff == await fetch_package_diff(osc, prj, pkg, revision=1)
    assert second_diff == await fetch_package_diff(osc, prj, pkg, revision=2)
