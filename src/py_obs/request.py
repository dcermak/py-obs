import asyncio
import enum
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from dataclasses import Field, dataclass, field
from typing import ClassVar, NoReturn, TypeVar, overload
import typing
from py_obs.history import fetch_package_history
from py_obs.osc import Osc
from py_obs.person import Person2

from py_obs.project import Package, Person, PersonRole, Project
from .xml_factory import MetaMixin, StrElementField


@enum.unique
class RequestStatus(enum.StrEnum):
    """Possible states of a Review of a request"""

    #:: The request has been reviewed
    REVIEW = enum.auto()
    #:  New request without any reviews
    NEW = enum.auto()
    #: The request has been accepted
    ACCEPTED = enum.auto()
    #: The request has been declined by the reviewer
    DECLINED = enum.auto()
    #: The request has been revoked by the submitter
    REVOKED = enum.auto()
    #: The request has been superseded by a new one
    SUPERSEDED = enum.auto()
    #: The request has been deleted
    DELETED = enum.auto()


@enum.unique
class RequestActionType(enum.StrEnum):
    """Which action should this request achieve?"""

    #: The request is the submission of a package to another project
    SUBMIT = enum.auto()
    #: Request to delete the project or package
    DELETE = enum.auto()
    #: Change the devel project of this package
    CHANGE_DEVEL = enum.auto()
    #: Add a user to the package or project
    ADD_ROLE = enum.auto()
    #: set the bugowner of the package or project
    SET_BUGOWNER = enum.auto()
    MAINTENANCE_INCIDENT = enum.auto()
    MAINTENANCE_RELEASE = enum.auto()
    GROUP = enum.auto()


@dataclass(frozen=True)
class RequestSource(MetaMixin):
    project: str
    package: str | None = None
    rev: str | None = None

    _element_name: ClassVar[str] = "source"


@dataclass(frozen=True)
class RequestTarget(MetaMixin):
    project: str
    package: str | None = None
    releaseproject: str | None = None
    repository: str | None = None

    _element_name: ClassVar[str] = "target"


@enum.unique
class SourceUpdate(enum.StrEnum):
    UPDATE = enum.auto()
    NOUPDATE = enum.auto()
    CLEANUP = enum.auto()


@dataclass(frozen=True)
class Options(MetaMixin):
    sourceupdate: SourceUpdate | None = None
    updatelink: bool | None = None
    makeoriginolder: bool | None = None

    _element_name: ClassVar[str] = "options"


T = TypeVar("T")


@dataclass(frozen=True)
class RequestAction(MetaMixin):
    type: RequestActionType

    #: Source of this request (required for submitrequests and maintenance releases)
    source: RequestSource | None = None
    #: target of this request, required for nearly everything
    target: RequestTarget | None = None

    #: User that is involved in role addition requests
    person: Person | None = None
    # #: Group that is involved in role addition requests
    # group: Group | None = None

    #: Additional options for this request
    options: Options | None = None

    # #: This field contains information about the result of this request once it is
    # #: accepted.
    # accept_info: AcceptInfo | None

    def field_transformer(
        self, field: Field[typing.Any]
    ) -> tuple[T, str, typing.Type[T]]:
        if field.name == "person":
            pers = (
                Person2(name=self.person.userid, role=self.person.role)
                if self.person
                else None
            )
            return pers, "person", Person2 | None  # type: ignore
        return super().field_transformer(field)

    @staticmethod
    def _person_from_entry(xml_element: ET.Element) -> Person | None:
        elem = xml_element.find("person")
        if elem:
            return Person(elem.attrib["name"], role=PersonRole(elem.attrib["role"]))
        return None

    _field_converters: typing.ClassVar[
        dict[str, typing.Callable[[ET.Element], typing.Any]] | None
    ] = {"person": _person_from_entry}

    _element_name: ClassVar[str] = "action"


@dataclass
class RequestState(MetaMixin):
    state: RequestStatus

    who: str | None = None
    when: str | None = None
    created: str | None = None
    superseded_by: int | None = None
    comment: StrElementField | None = None
    approver: str | None = None

    def field_transformer(
        self, field: Field[typing.Any]
    ) -> tuple[T, str, typing.Type[T]]:
        if field.name == "state":
            return self.state, "name", RequestStatus  # type: ignore
        return super().field_transformer(field)

    _field_converters: typing.ClassVar[
        dict[str, typing.Callable[[ET.Element], typing.Any]] | None
    ] = {"state": lambda elem: RequestStatus(elem.attrib["name"])}

    _element_name: ClassVar[str] = "state"


@dataclass(frozen=True)
class Request(MetaMixin):
    """Representation of a request in the Open Build Service"""

    #: Unique identifier of this request.
    id: int | None

    #: User id of the creator of this request.
    creator: str | None

    #: Optional description of this request
    description: list[str] | None = None

    #: Set of actions that will be performed once the request is accepted
    action: list[RequestAction] = field(default_factory=list)

    #: The state of this request
    state: RequestState | None = None

    #: Optional priority of this request
    # priority: ObsRatings|None = None

    #: History of this request
    # history: RequestHistory[] = field(default_factory=list)

    #: Administrators can set this field which specifies when this request will
    #: be automatically accepted (it can still be declined).
    # autoAcceptAt?: Date;

    #: Reviews for this request.
    # reviews: RequestReview[]

    _element_name: ClassVar[str] = "request"


@dataclass(frozen=True)
class _RequestCollection(MetaMixin):
    matches: int

    request: list[Request] = field(default_factory=list)

    _element_name: typing.ClassVar[str] = "collection"


def _request_base_route(
    request: Request | None = None, request_id: int | None = None
) -> str:
    assert request or request_id
    if request is not None and request.id is None:
        raise ValueError("Cannot handle a request without an id")
    return f"/request/{request.id if request else request_id}"


@overload
async def fetch_request(osc: Osc, *, request: Request) -> Request: ...


@overload
async def fetch_request(osc: Osc, *, request_id: int) -> Request: ...


async def fetch_request(
    osc: Osc, request: Request | None = None, request_id: int | None = None
) -> Request:
    return await Request.from_response(
        await osc.api_request(_request_base_route(request, request_id))
    )


@overload
async def search_for_requests(
    osc: Osc,
) -> NoReturn: ...


@overload
async def search_for_requests(
    osc: Osc,
    *,
    user: str | None = None,
    project: str | Project | None = None,
    package: str | Package | None = None,
    states: list[RequestStatus] | None = None,
    roles: list[PersonRole] | None = None,
    ids: list[int] | None = None,
    types: list[RequestActionType] | None = None,
) -> list[Request]: ...


async def search_for_requests(
    osc: Osc,
    *,
    user: str | None = None,
    project: str | Project | None = None,
    package: str | Package | None = None,
    states: list[RequestStatus] | None = None,
    roles: list[PersonRole] | None = None,
    ids: list[int] | None = None,
    types: list[RequestActionType] | None = None,
) -> list[Request]:
    """Search for requests by any combination of the following parameters:
    - userid
    - project
    - package
    - request states (if not provided, then search for requests in state new or
      review)
    - roles of the request creator
    - request type
    """
    route = "/request?view=collection"
    query: list[tuple[str, str]] = [("view", "collection")]

    assert user or project or package or states or roles or ids or types

    if states is None:
        states = [RequestStatus.NEW, RequestStatus.REVIEW]

    if user:
        query.append(("user", user))
    if project:
        query.append(
            ("project", project.name if isinstance(project, Project) else project)
        )
    if package:
        query.append(
            ("package", package.name if isinstance(package, Package) else package)
        )
    if states:
        query.append(("states", ",".join(str(s) for s in states)))
    if roles:
        query.append(("roles", ",".join(str(r) for r in roles)))
    if ids:
        query.append(("ids", ",".join(str(id) for id in ids)))
    if types:
        query.append(("types", ",".join(str(t) for t in types)))

    route = f"/request?{urlencode(query=query)}"

    res = await osc.api_request(route=route, method="GET")

    return _RequestCollection.from_xml(ET.fromstring(await res.read())).request


@enum.unique
class PackageRevision(enum.Enum):
    #: use the latest revision
    LATEST = enum.auto()


async def submit_package(
    osc: Osc,
    source_prj: str | Project,
    pkg: str | Package,
    dest_prj: str | Project,
    dest_pkg: str | Package | None = None,
    description: str = "",
    supersede_old_request: bool = True,
    requests_to_supersede: list[Request | int] | None = None,
    revision: str | PackageRevision | None = None,
) -> Request:
    """Create a new submitrequest of the package ``pkg`` from the source project
    ``source_prj`` to the destination ``dest_prj``. If the destination package
    ``dest_pkg`` is supplied, use that package name instead of the source
    package name.

    If ``supersede_old_request`` is `True`, **all** submit requests to the
    destination package by this user will be superseded.

    If a list of requests that shall be superseded is supplied, then those
    requests will be superseded by the newly created request.

    Both ``supersede_old_request`` and ``requests_to_supersede`` can be provided
    at the same time.

    The ``revision`` argument can optionally be provided to specify the exact
    revision which should be submitted. By default no revision is specified. If
    the value is :py:attr:`~py_obs.request.PackageRevision.LATEST`, then the
    srcmd5 of the latest revision of the source package will be used.

    """
    ACTION = RequestActionType.SUBMIT

    src_prj_name: str = source_prj if isinstance(source_prj, str) else source_prj.name
    src_pkg_name: str = pkg if isinstance(pkg, str) else pkg.name
    dest_pkg_name: str = (
        src_pkg_name
        if dest_pkg is None
        else (dest_pkg if isinstance(dest_pkg, str) else dest_pkg.name)
    )

    rev: str | None = None
    if isinstance(revision, PackageRevision):
        assert revision == PackageRevision.LATEST

        hist = await fetch_package_history(osc, source_prj, pkg, limit=1)
        if not hist:
            raise ValueError(
                f"Package {src_prj_name}/{src_pkg_name} has no history, cannot obtain srcmd5"
            )

        if not (rev := hist[0].srcmd5):
            raise ValueError(
                "HEAD of package {src_prj_name}/{src_pkg_name} has no srcmd5"
            )

    else:
        rev = revision

    rq = Request(
        id=None,
        creator=osc.username,
        description=[description] if description else None,
        action=[
            RequestAction(
                type=ACTION,
                source=RequestSource(
                    project=src_prj_name, package=src_pkg_name, rev=rev
                ),
                target=RequestTarget(
                    project=(dest_prj if isinstance(dest_prj, str) else dest_prj.name),
                    package=dest_pkg_name,
                ),
            )
        ],
    )
    res = await osc.api_request(
        route="/request/",
        params={"cmd": "create"},
        method="POST",
        payload=ET.tostring(rq.meta),
    )

    created_request = Request.from_xml(ET.fromstring(await res.read()))

    to_supersede_ids = []

    if supersede_old_request:
        requests = await search_for_requests(
            osc,
            user=osc.username,
            project=dest_prj,
            package=dest_pkg or pkg,
            types=[ACTION],
            states=[RequestStatus.NEW, RequestStatus.REVIEW],
        )
        for request in requests:
            # don't try to supersede the just created request
            # and don't bother trying to supersede somebody else' request
            if request.id == created_request.id or request.creator != osc.username:
                continue

            to_supersede_ids.append(request.id)

    for req in requests_to_supersede or []:
        if isinstance(req, Request):
            to_supersede_ids.append(req.id)
        else:
            to_supersede_ids.append(req)

    tasks = []
    for rq_id in set(to_supersede_ids):
        route = f"/request/{rq_id}?" + urlencode(
            query=[
                ("cmd", "changestate"),
                ("newstate", RequestStatus.SUPERSEDED),
                ("superseded_by", created_request.id),
            ]
        )
        tasks.append(osc.api_request(method="POST", route=route))

    await asyncio.gather(*tasks)

    return created_request


@overload
async def change_state(
    osc: Osc, *, request: Request, new_state: RequestStatus, comment: str | None = None
) -> None: ...


@overload
async def change_state(
    osc: Osc, *, request_id: int, new_state: RequestStatus, comment: str | None = None
) -> None: ...


async def change_state(
    osc: Osc,
    *,
    request_id: int | None = None,
    request: Request | None = None,
    new_state: RequestStatus,
    comment: str | None = None,
) -> None:
    assert request or request_id

    route = _request_base_route(request, request_id)
    params = {"cmd": "changestate", "newstate": str(new_state)}
    if comment:
        params["comment"] = comment

    await osc.api_request(route, method="POST", params=params)


@overload
async def delete(osc: Osc, *, request: Request, comment: str | None = None) -> None: ...


@overload
async def delete(osc: Osc, *, request_id: int, comment: str | None = None) -> None: ...


async def delete(
    osc: Osc,
    *,
    request: Request | None = None,
    request_id: int | None = None,
    comment: str | None = None,
) -> None:
    assert request or request_id

    await osc.api_request(
        route=_request_base_route(request, request_id),
        method="DELETE",
        params={} if not comment else {"comment": comment},
    )
