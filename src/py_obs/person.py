import enum
from dataclasses import dataclass
from dataclasses import field
from typing import ClassVar

from py_obs.osc import Osc
from py_obs.xml_factory import MetaMixin
from py_obs.xml_factory import StrElementField


@enum.unique
class PersonRole(enum.StrEnum):
    BUGOWNER = enum.auto()
    MAINTAINER = enum.auto()
    READER = enum.auto()


@dataclass(frozen=True)
class Person(MetaMixin):
    userid: str
    role: PersonRole = PersonRole.MAINTAINER

    _element_name: ClassVar[str] = "person"


@dataclass(frozen=True)
class Person2(MetaMixin):
    name: str
    role: PersonRole = PersonRole.MAINTAINER

    _element_name: ClassVar[str] = "person"

    def to_person(self) -> Person:
        return Person(userid=self.name, role=self.role)


@dataclass(frozen=True)
class User(MetaMixin):
    login: StrElementField
    email: StrElementField | None
    realname: StrElementField | None
    state: StrElementField | None

    _element_name: ClassVar[str] = "person"


@dataclass(frozen=True)
class UserGroup(MetaMixin):
    @dataclass(frozen=True)
    class GroupMaintainer(MetaMixin):
        _element_name: ClassVar[str] = "maintainer"
        userid: str

    @dataclass(frozen=True)
    class GroupPerson(MetaMixin):
        @dataclass(frozen=True)
        class GroupPersonEntry(MetaMixin):
            _element_name: ClassVar[str] = "person"
            userid: str

        _element_name: ClassVar[str] = "person"
        person: list[GroupPersonEntry]

    title: StrElementField
    email: StrElementField | None

    person: GroupPerson
    maintainer: list[GroupMaintainer] = field(default_factory=list)

    _element_name: ClassVar[str] = "group"


@dataclass(frozen=True)
class Group(MetaMixin):
    _element_name: ClassVar[str] = "group"

    name: str
    role: PersonRole = PersonRole.MAINTAINER


async def fetch_user(osc: Osc, username: str) -> User:
    return await User.from_response(
        await osc.api_request(f"/person/{username}", method="GET")
    )


async def fetch_group(osc: Osc, groupname: str) -> UserGroup:
    return await UserGroup.from_response(
        await osc.api_request(f"/group/{groupname}", method="GET")
    )


@dataclass(frozen=True)
class Owner(MetaMixin):
    project: str
    package: str | None = None

    person: list[Person2] = field(default_factory=list)

    group: list[Group] = field(default_factory=list)

    _element_name: ClassVar[str] = "owner"


@dataclass(frozen=True)
class OwnerCollection(MetaMixin):
    _element_name: ClassVar[str] = "collection"

    owner: list[Owner] = field(default_factory=list)
