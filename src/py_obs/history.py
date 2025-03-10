import datetime
import typing
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import ClassVar

from py_obs.osc import Osc
from py_obs.project import Package
from py_obs.project import Project
from py_obs.xml_factory import MetaMixin
from py_obs.xml_factory import StrElementField


@dataclass(frozen=True)
class Revision(MetaMixin):
    """A revision of a package or its metadata"""

    #: revision number of this commit
    rev: int

    #: strictly increasing number for a given version that is reset to zero on
    #: each version bump
    vrev: int

    srcmd5: StrElementField

    version: StrElementField

    time: datetime.datetime

    #: committer
    user: StrElementField

    #: commit message
    comment: StrElementField | None = None

    _element_name: ClassVar[str] = "revision"

    @staticmethod
    def _datetime_from_xml(xml_element: ET.Element) -> datetime.datetime | None:
        if (elem := xml_element.find("time")) is not None:
            return datetime.datetime.fromtimestamp(float(elem.text or "0"))
        return None

    _field_converters: typing.ClassVar[
        dict[str, typing.Callable[[ET.Element], typing.Any]] | None
    ] = {"time": _datetime_from_xml}


@dataclass(frozen=True)
class _RevisionList(MetaMixin):
    """The commit history of a package"""

    revision: list[Revision]

    _element_name: ClassVar[str] = "revisionlist"


async def fetch_package_history(
    osc: Osc,
    project: str | Project,
    package: str | Package,
    *,
    limit: int | None = None,
    deleted: bool = False,
    meta: bool = False,
) -> list[Revision]:
    """Fetch the history of a package in the specified project.

    Parameters
    ----------
    limit: only return the n newest revisions
    deleted: fetch the history of a deleted package
    meta: don't fetch the package history but the history of the metadata

    """
    params = {}
    if meta:
        params["meta"] = "1"
    if deleted:
        params["deleted"] = "1"
    if limit:
        params["limit"] = str(limit)

    prj_name = project.name if isinstance(project, Project) else project
    pkg_name = package.name if isinstance(package, Package) else package

    return (
        await _RevisionList.from_response(
            await osc.api_request(
                f"/source/{prj_name}/{pkg_name}/_history", params=params
            )
        )
    ).revision
