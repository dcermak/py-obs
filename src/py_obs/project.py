import asyncio
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import ClassVar, cast, overload
import xml.etree.ElementTree as ET

from py_obs.osc import Osc
from py_obs.person import (
    OwnerCollection,
    Person,
    Person2,
    PersonRole,
    UserGroup,
    fetch_group,
)
from py_obs.status import Status
from .xml_factory import MetaMixin, StrElementField


@dataclass(frozen=True)
class PathEntry(MetaMixin):
    project: str
    repository: str

    _element_name: ClassVar[str] = "path"


class RebuildMode(StrEnum):
    """Rebuild modes of a repository."""

    #: default: build on source change and all depending packages including
    #: indirect dependencies
    TRANSITIVE = auto()

    #: build on source change and direct depending packages
    DIRECT = auto()

    #: build on source change only
    LOCAL = auto()


@dataclass(frozen=True)
class Repository(MetaMixin):
    name: str
    rebuild: RebuildMode | None = None
    path: list[PathEntry] | None = None
    arch: list[str] | None = None

    _element_name: ClassVar[str] = "repository"


@dataclass(frozen=True)
class DevelProject(MetaMixin):
    project: str
    package: str

    _element_name: ClassVar[str] = "devel"


@dataclass(frozen=True)
class Project(MetaMixin):
    name: str
    title: StrElementField
    description: StrElementField = StrElementField("")

    person: list[Person] | None = None
    repository: list[Repository] | None = None

    _element_name: ClassVar[str] = "project"


@dataclass(frozen=True)
class Package(MetaMixin):
    name: str
    title: StrElementField
    description: StrElementField = StrElementField("")

    person: list[Person] | None = None
    scmsync: StrElementField | None = None
    devel: DevelProject | None = None
    url: StrElementField | None = None

    _element_name: ClassVar[str] = "package"


@dataclass(frozen=True)
class PackageMaintainers:
    package: list[Person2] = field(default_factory=list)
    project: list[Person2] = field(default_factory=list)


@overload
async def search_for_maintainers(
    osc: Osc,
    *,
    pkg: Package,
    roles: list[PersonRole] | None = None,
    groups_to_ignore: list[str] | None = None,
) -> PackageMaintainers: ...


@overload
async def search_for_maintainers(
    osc: Osc,
    *,
    pkg_name: str,
    roles: list[PersonRole] | None = None,
    groups_to_ignore: list[str] | None = None,
) -> PackageMaintainers: ...


async def search_for_maintainers(
    osc: Osc,
    *,
    pkg: Package | None = None,
    pkg_name: str | None = None,
    roles: list[PersonRole] | None = None,
    groups_to_ignore: list[str] | None = None,
) -> PackageMaintainers:
    """Query the build service to find the maintainers of the package provided
    either by name or via a :py:class:`Package` instance.

    This function includes the maintainers from groups in the result.
    You can exclude the members from specific groups to be added to the results
    by adding the groupname to the ``groups_to_ignore`` parameter. This can be
    used to exclude e.g. ``factory-maintainers`` who are listed as
    co-maintainers for every package in ``openSUSE:Factory``.
    """

    if not pkg_name:
        assert pkg
        pkg_name = pkg.name

    if groups_to_ignore is None:
        groups_to_ignore = []

    params = {"package": pkg_name}
    if roles:
        params["filter"] = ",".join(roles)

    owners = await OwnerCollection.from_response(
        await osc.api_request("/search/owner", method="GET", params=params)
    )

    pkg_maintainers = []
    prj_maintainers = []
    for owner in owners.owner:

        async def fetch_group_members() -> list[Person2]:
            tasks = []
            for grp in owner.group:
                if grp.name not in groups_to_ignore:
                    tasks.append(fetch_group(osc, grp.name))

            res = cast(tuple[UserGroup], await asyncio.gather(*tasks))
            return [
                Person2(maint.userid) for grp in res for maint in grp.maintainer
            ] + [Person2(pers.userid) for grp in res for pers in grp.person.person]

        if owner.project and owner.package == pkg_name:
            pkg_maintainers.extend(owner.person)
            pkg_maintainers.extend(await fetch_group_members())

        if owner.project and not owner.package:
            prj_maintainers.extend(owner.person)
            prj_maintainers.extend(await fetch_group_members())

    return PackageMaintainers(
        package=list(set(pkg_maintainers)), project=list(set(prj_maintainers))
    )


@overload
async def send_meta(osc: Osc, *, prj: Project) -> None: ...


@overload
async def send_meta(osc: Osc, *, prj: Project, pkg: Package) -> None: ...


@overload
async def send_meta(osc: Osc, *, prj_name: str, prj_meta: ET.Element) -> None: ...


@overload
async def send_meta(
    osc: Osc, *, prj_name: str, pkg_name: str, pkg_meta: ET.Element
) -> None: ...


async def send_meta(
    osc: Osc,
    *,
    prj: Project | None = None,
    prj_name: str | None = None,
    prj_meta: ET.Element | None = None,
    pkg: Package | None = None,
    pkg_name: str | None = None,
    pkg_meta: ET.Element | None = None,
) -> None:
    route = "/source/"

    if prj and pkg:
        route += f"{prj.name}/{pkg.name}"
        meta = pkg.meta
    elif prj and not pkg:
        route += prj.name
        meta = prj.meta
    elif prj_name and pkg_name and pkg_meta:
        route += f"{prj_name}/{pkg_name}"
        meta = pkg_meta
    elif prj_name and prj_meta:
        route += prj_name
        meta = prj_meta
    else:
        assert False, "Invalid parameter combination"

    route += "/_meta"

    await osc.api_request(route=route, payload=ET.tostring(meta), method="PUT")


@overload
async def delete(osc: Osc, *, prj: Project | str, force: bool = False) -> None: ...


@overload
async def delete(
    osc: Osc, *, prj: Project | str, pkg: Package | str, force: bool = False
) -> None: ...


async def delete(
    osc: Osc,
    *,
    prj: Project | str,
    pkg: Package | str | None = None,
    force: bool = False,
) -> None:
    prj_name = prj.name if isinstance(prj, Project) else prj
    route = f"/source/{prj_name}/"
    if pkg:
        route += pkg.name if isinstance(pkg, Package) else pkg

    await osc.api_request(
        route, method="DELETE", params={"force": "1"} if force else None
    )


@overload
async def fetch_meta(osc: Osc, *, prj: Project | str) -> Project: ...


@overload
async def fetch_meta(
    osc: Osc, *, prj: Project | str, pkg: Package | str
) -> Package: ...


async def fetch_meta(
    osc: Osc, *, prj: Project | str, pkg: Package | str | None = None
) -> Project | Package:
    """Fetch the config (aka the ``_meta``) of a package or project and return
    an instance of :py:class:`Project` or :py:class`Package` depending on
    whether the ``pkg`` parameter was supplied or not.

    """
    route = f"/source/{prj.name if isinstance(prj, Project) else prj}"

    if pkg:
        route += f"/{pkg.name if isinstance(pkg, Package) else pkg}"

    route += "/_meta"

    if pkg:
        return await Package.from_response(await osc.api_request(route))

    return await Project.from_response(await osc.api_request(route))


@dataclass(frozen=True)
class _Directory(MetaMixin):
    @dataclass(frozen=True)
    class Entry(MetaMixin):
        _element_name: ClassVar[str] = "entry"

        name: str | None
        md5: str | None
        size: int | None
        mtime: int | None
        originproject: str | None
        originpackage: str | None
        available: bool | None
        recommended: bool | None
        hash: str | None

    @dataclass(frozen=True)
    class LinkInfo(MetaMixin):
        _element_name: ClassVar[str] = "linkinfo"

        project: str | None
        package: str | None
        srcmd5: str | None
        rev: str | None
        baserev: str | None
        xsrcmd5: str | None
        lsrcmd5: str | None
        error: str | None

    @dataclass(frozen=True)
    class ServiceInfo(MetaMixin):
        _element_name: ClassVar[str] = "serviceinfo"
        code: str | None
        error: str | None
        lsrcmd5: str | None
        xsrcmd5: str | None

    _element_name: ClassVar[str] = "directory"

    name: str | None
    rev: str | None
    vrev: str | None
    srcmd5: str | None
    count: int | None

    entry: list[Entry]
    linkinfo: list[LinkInfo]
    serviceinfo: list[ServiceInfo]


def _prj_and_pkg_name(prj: str | Project, pkg: Package | str) -> tuple[str, str]:
    return (
        prj.name if isinstance(prj, Project) else prj,
        pkg.name if isinstance(pkg, Package) else pkg,
    )


async def fetch_package_list(
    osc: Osc, project: Project | str, *, exclude_multibuild_flavors: bool = True
) -> list[str]:
    """Retrieve the list of packages in the supplied project.

    If exclude_multibuild_flavors is ``True``, then flavors of multibuild
    packages are not shown and only the main package names are displayed.

    """
    dentries = [
        entry
        for entry in (
            await _Directory.from_response(
                await osc.api_request(
                    f"/source/{project.name if isinstance(project, Project) else project}"
                )
            )
        ).entry
    ]

    if not exclude_multibuild_flavors:
        return [d.name for d in dentries if d.name]

    res = []
    for dentry in dentries:
        if dentry.name:
            if ":" in dentry.name and dentry.originpackage:
                res.append(dentry.originpackage)
            else:
                res.append(dentry.name.partition(":")[0])
    return list(set(res))


@dataclass(frozen=True)
class File:
    #: The file name
    name: str

    #: MD5 Hash of the file contents
    md5_sum: str

    #: file size in bytes
    size: int

    #: Unix time of the last modification
    mtime: int


async def fetch_file_list(
    osc: Osc, prj: str | Project, pkg: Package | str, expand_links: bool = True
) -> list[File]:
    """Fetch the list of files of a package in the given project."""
    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)

    return [
        File(name=entry.name, md5_sum=entry.md5, size=entry.size, mtime=entry.mtime)
        for entry in (
            await _Directory.from_response(
                await osc.api_request(
                    route=f"/source/{prj_name}/{pkg_name}",
                    params={"expand": "1"} if expand_links else None,
                )
            )
        ).entry
        if entry.name and entry.md5 and entry.size and entry.mtime
    ]


async def fetch_file_contents(
    osc: Osc,
    prj: str | Project,
    pkg: Package | str,
    file: str | File,
    expand_links: bool = True,
) -> bytes:
    """Fetch the contents of a file on OBS"""
    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)
    fname = file.name if isinstance(file, File) else file

    return await (
        await osc.api_request(
            f"/source/{prj_name}/{pkg_name}/{fname}",
            params={"expand": "1"} if expand_links else None,
        )
    ).read()


async def upload_file_contents(
    osc: Osc,
    prj: str | Project,
    pkg: Package | str,
    file: str | File,
    new_contents: bytes | str,
    keeplink: bool = True,
) -> None:
    """Upload the contents for the given file. This implicitly creates a new
    commit.

    """
    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)
    fname = file.name if isinstance(file, File) else file

    await osc.api_request(
        f"/source/{prj_name}/{pkg_name}/{fname}",
        method="PUT",
        payload=new_contents,
        params={"keeplink": "1" if keeplink else "0"},
    )


async def fetch_all_files(
    osc: Osc, prj: str | Project, pkg: Package | str, expand_links: bool = True
) -> dict[str, bytes]:
    """Retrieve all files for the given package. Returns a dictionary where the
    file name is the key and the file contents the value.

    """
    res = {}

    tasks = []
    for file in await fetch_file_list(osc, prj, pkg, expand_links):

        async def _fetch_cur_file(f: File) -> None:
            res[f.name] = await fetch_file_contents(osc, prj, pkg, f, expand_links)

        tasks.append(_fetch_cur_file(file))

    await asyncio.gather(*tasks)

    return res


async def fetch_package_diff(
    osc: Osc,
    prj: str | Project,
    pkg: Package | str,
    expand_links: bool = True,
    limit_to_files: list[str] | None = None,
    revision: int | str | None = None,
) -> str:
    """Fetch the server side rendered diff of a package.

    Parameters:
    - prj, pkg: the package to diff
    - expand_links: whether package links should be expanded before diffing
    - limit_to_files: only display the diff of the selected files
    - revision: specify the revision, which diff should be displayed. Defaults
      to the latest revision
    """
    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)
    params: dict[str, str | list[str]] = {
        "cmd": "diff",
        "filelimit": "0",
        "expand": "1" if expand_links else "0",
    }
    if limit_to_files:
        params["file[]"] = limit_to_files

    if revision:
        params["rev"] = str(revision)

    return (
        await (
            await osc.api_request(
                f"/source/{prj_name}/{pkg_name}",
                method="POST",
                params=params,
            )
        ).read()
    ).decode()


async def branch_package(
    osc: Osc,
    prj: str | Project,
    pkg: Package | str,
    target_project: str | Project = "",
    target_package: str | Package = "",
) -> tuple[str, str]:
    """Create a branched package of the package `prj/pkg`. Optionally it is
    possible to specify a target package and/or a target project. If no values
    are given, then the target package name is equal to the original package
    name and the target project name is `home:$username:branches:$prj`.

    """

    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)
    params = {
        "cmd": "branch",
        "package": pkg_name,
        "project": prj_name,
        "update_project_attribute": "OBS:UpdateProject",
    }

    if target_project:
        params["target_project"] = (
            target_project if isinstance(target_project, str) else target_project.name
        )

    if target_package:
        params["target_package"] = (
            target_package if isinstance(target_package, str) else target_package.name
        )

    branch_status = await Status.from_response(
        await osc.api_request("/source", params=params, method="POST")
    )

    target_prj = branch_status.data.get(tgt_prj_key := "targetproject")
    target_pkg = branch_status.data.get(tgt_pkg_key := "targetpackage")

    if not target_prj:
        raise RuntimeError(f"{tgt_prj_key} entry missing from OBS status")
    if not target_pkg:
        raise RuntimeError(f"{tgt_pkg_key} entry missing from OBS status")

    return (target_prj if isinstance(target_prj, str) else target_prj[0]), (
        target_pkg if isinstance(target_pkg, str) else target_pkg[0]
    )


@dataclass(frozen=True)
class PackageSourceInfo(MetaMixin):
    """Source information of a rpm-spec based package."""

    #: The package name
    package: str

    #: package source revision
    rev: str
    #: strictly increasing revision counter per package version
    vrev: str

    #: source package md5 hash
    srcmd5: str

    #: filename of the spec file/build recipe that was used
    filename: StrElementField

    #: name of the main package
    name: StrElementField

    #: main package version
    version: StrElementField

    #: main package release
    release: StrElementField

    #: project from which this package has been linked in
    originproject: StrElementField | None = None

    #: list of subpackages
    subpacks: list[str] = field(default_factory=list)

    #: list of dependent packages
    deps: list[str] = field(default_factory=list)

    #: Package build prerequisites
    prereqs: list[str] = field(default_factory=list)

    _element_name: ClassVar[str] = "sourceinfo"


@dataclass(frozen=True)
class _BrokenPackageSourceInfo(MetaMixin):
    """Required due to
    https://github.com/openSUSE/open-build-service/issues/16233.

    This is the representation of an "error" response from OBS for packages that
    are not spec files.

    """

    #: filename of the spec file/build recipe that was used
    error: StrElementField

    _element_name: ClassVar[str] = "sourceinfo"


async def fetch_package_info(
    osc: Osc,
    prj: str | Project,
    pkg: Package | str,
) -> PackageSourceInfo:
    """Fetch the sourceinfo of a package from the buildservice. Includes
    extended information like dependencies, linked projects, subpackages,
    version, etc.

    """
    prj_name, pkg_name = _prj_and_pkg_name(prj, pkg)

    data = await (
        await osc.api_request(
            f"/source/{prj_name}/{pkg_name}", params={"view": "info", "parse": "1"}
        )
    ).read()

    try:
        return PackageSourceInfo.from_xml(data)
    except (ValueError, KeyError):
        err = (_BrokenPackageSourceInfo.from_xml(data)).error
        raise ValueError(
            f"OBS could not parse the package {prj_name}/{pkg_name}: {err}"
        )
