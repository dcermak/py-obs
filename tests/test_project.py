import xml.etree.ElementTree as ET
import pytest
from py_obs.person import PersonRole
from py_obs.project import (
    PathEntry,
    Person,
    Project,
    RebuildMode,
    Repository,
    fetch_meta,
)
from py_obs.xml_factory import StrElementField
from tests.conftest import HOME_PROJ_T


@pytest.mark.parametrize(
    "project,prj_meta",
    [
        (
            Project(
                name="home:defolos:BCI:CR:SLE-15-SP4",
                title=StrElementField("BCI Development project for SLE 15 SP4"),
                person=[
                    Person(userid="fcrozat", role=PersonRole.BUGOWNER),
                    Person(userid="aherzig", role=PersonRole.MAINTAINER),
                ],
                repository=[
                    Repository(
                        name="standard",
                        path=[
                            PathEntry(project="SUSE:Registry", repository="standard"),
                            PathEntry(
                                project="SUSE:SLE-15-SP4:Update", repository="standard"
                            ),
                        ],
                        arch=["x86_64", "aarch64", "s390x", "ppc64le"],
                    ),
                    Repository(
                        name="images",
                        rebuild=RebuildMode.LOCAL,
                        path=[
                            PathEntry(
                                project="SUSE:SLE-15-SP4:Update", repository="images"
                            ),
                        ],
                        arch=["x86_64", "aarch64", "s390x", "ppc64le"],
                    ),
                ],
            ),
            """<project name="home:defolos:BCI:CR:SLE-15-SP4"><title>BCI Development project for SLE 15 SP4</title><description/><person userid="fcrozat" role="bugowner"/><person userid="aherzig" role="maintainer"/><repository name="standard"><path project="SUSE:Registry" repository="standard"/><path project="SUSE:SLE-15-SP4:Update" repository="standard"/><arch>x86_64</arch><arch>aarch64</arch><arch>s390x</arch><arch>ppc64le</arch></repository><repository name="images" rebuild="local"><path project="SUSE:SLE-15-SP4:Update" repository="images"/><arch>x86_64</arch><arch>aarch64</arch><arch>s390x</arch><arch>ppc64le</arch></repository></project>""",
        )
    ],
)
def test_project(project: Project, prj_meta: str):
    assert ET.canonicalize(
        ET.tostring(project.meta, short_empty_elements=True).decode("utf-8")
    ) == ET.canonicalize(prj_meta)


@pytest.mark.asyncio
async def test_fetch_project_meta(home_project: HOME_PROJ_T):
    async for osc, admin_osc, prj, _ in home_project:
        for osc_ in osc, admin_osc:
            assert await fetch_meta(osc_, prj=prj) == prj
            assert await fetch_meta(osc_, prj=prj.name) == prj
