from dataclasses import dataclass
from enum import StrEnum, auto
from typing import ClassVar
from py_obs.osc import Osc
from py_obs.xml_factory import MetaMixin


class PackageCode(StrEnum):
    UNRESOLVABLE = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    BROKEN = auto()
    DISABLED = auto()
    EXCLUDED = auto()
    BLOCKED = auto()
    LOCKED = auto()
    UNKNOWN = auto()
    SCHEDULED = auto()
    BUILDING = auto()
    FINISHED = auto()


@dataclass(frozen=True)
class PackageStatus(MetaMixin):
    _element_name: ClassVar[str] = "status"

    package: str
    code: PackageCode

    details: list[str]


class RepositoryCode(StrEnum):
    UNKNOWN = auto()
    BROKEN = auto()
    SCHEDULING = auto()
    BLOCKED = auto()
    BUILDING = auto()
    FINISHED = auto()
    PUBLISHING = auto()
    PUBLISHED = auto()
    UNPUBLISHED = auto()


@dataclass(frozen=True)
class BuildResult(MetaMixin):
    _element_name: ClassVar[str] = "result"

    project: str
    repository: str
    arch: str
    state: RepositoryCode
    code: RepositoryCode
    dirty: bool | None

    status: list[PackageStatus]


@dataclass(frozen=True)
class BuildResultList(MetaMixin):
    _element_name: ClassVar[str] = "resultlist"

    result: list[BuildResult]


async def fetch_build_result(
    osc: Osc,
    project_name: str,
    package_name: str,
    *,
    lastbuild: bool = False,
    multibuild: bool = True,
    locallink: bool = True,
) -> list[BuildResult]:
    """Fetches the build results of a package.

    Parameters:
    -----------

    - locallink: set to ``True`` to include build results from packages with
      project local links.

    - lastbuild: Set to ``True`` to show the last build result (excludes current
      building job states).

    - multibuild: Set to ``True`` to include build results from
      :file:`_multibuild` definitions

    """
    return (
        await BuildResultList.from_response(
            await osc.api_request(
                f"/build/{project_name}/_result",
                params={
                    "view": "status",
                    "multibuild": str(int(multibuild)),
                    "locallink": str(int(locallink)),
                    "package": package_name,
                    "lastbuild": str(int(lastbuild)),
                },
            )
        )
    ).result
