import xml.etree.ElementTree as ET
import pytest
from py_obs.person import PersonRole
from py_obs.project import (
    Package,
    PathEntry,
    Person,
    Project,
    RebuildMode,
    Repository,
    fetch_meta,
    fetch_package_list,
    send_meta,
)
from py_obs.xml_factory import StrElementField
from tests.conftest import HOME_PROJ_T, OSC_FROM_ENV_T


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
    osc, admin_osc, prj, _ = home_project
    for osc_ in osc, admin_osc:
        assert await fetch_meta(osc_, prj=prj) == prj
        assert await fetch_meta(osc_, prj=prj.name) == prj


@pytest.mark.asyncio
async def test_fetch_package_list(home_project: HOME_PROJ_T):
    osc, _, prj, pkg = home_project
    assert (await fetch_package_list(osc, prj)) == [pkg.name]

    await send_meta(
        osc, prj=prj, pkg=Package("vim", title=StrElementField("vim editor"))
    )

    assert (
        "vim" in (new_pkg_list := await fetch_package_list(osc, prj))
        and pkg.name in new_pkg_list
        and len(new_pkg_list) == 2
    )


@pytest.mark.vcr(filter_headers=["authorization", "openSUSE_session"])
@pytest.mark.asyncio
async def test_package_list_excludes_multibuild(osc_from_env: OSC_FROM_ENV_T) -> None:
    pkg_list = await fetch_package_list(
        osc_from_env, "openSUSE.org:devel:BCI:SLE-15-SP6"
    )
    assert "sac-apache-tomcat-10-image" in pkg_list

    assert (
        len([pkg_with_colon for pkg_with_colon in pkg_list if ":" in pkg_with_colon])
        == 0
    )

    pkg_list_with_multibuild = await fetch_package_list(
        osc_from_env,
        "openSUSE.org:devel:BCI:SLE-15-SP6",
        exclude_multibuild_flavors=False,
    )
    assert len(pkg_list) < len(pkg_list_with_multibuild)
    assert "sac-apache-tomcat-10-image" in pkg_list_with_multibuild
    assert "sac-apache-tomcat-10-image:openjdk17" in pkg_list_with_multibuild
