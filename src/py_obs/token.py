"""Module for handling tokens

Tokens can be used to trigger specific actions on OBS without using your full
credentials. The main data structure of this module is the :py:class:`Token`
class representing a single token bound to a specific user. Ordinary users can
only read & modify their own tokens. The only exceptions are administrators who
have access to the tokens of every user. Hence all of the functions for reading
& writing tokens support omitting the username and default to
:py:attr:`Osc.username` as that is the only possible value for
non-administrators.

"""

from dataclasses import dataclass
from enum import StrEnum, auto, unique
from typing import ClassVar, Literal, overload
from py_obs.osc import Osc
from py_obs.status import Status

from py_obs.xml_factory import MetaMixin


@unique
class TokenKind(StrEnum):
    """Different types of tokens"""

    #: trigger SCM/CI workflows
    WORKFLOW = auto()

    #: retrieve the user's RSS feed
    RSS = auto()

    #: rebuild a package
    REBUILD = auto()

    #: trigger a release
    RELEASE = auto()

    #: run services
    # has to be temporarily overwritten because the OBS API is inconsistent:
    # https://github.com/openSUSE/open-build-service/issues/15078
    RUNSERVICE = "service"


@dataclass(frozen=True)
class Token(MetaMixin):
    """A token that can be used to trigger certain actions without supplying a
    username & password.

    """

    _element_name = "entry"

    #: internal token id
    id: int

    #: the token secret
    string: str

    #: the operation that this token supports
    kind: TokenKind

    #: timestamp when it was last triggered
    triggered_at: str

    #: optional project to which this token is bound
    project: str | None = None

    #: optional package to which this token is bound
    package: str | None = None

    #: description field of this token
    description: str = ""


@dataclass(frozen=True)
class _TokenDirectory(MetaMixin):
    _element_name: ClassVar[str] = "directory"

    #: number of tokens
    count: int

    #: tokens of the user
    entry: list[Token]


async def fetch_user_tokens(osc: Osc, username: str | None = None) -> list[Token]:
    """Fetch all tokens belonging to the user with the provided username. If no
    username is supplied, then the username of ``osc`` is used.

    """
    return (
        await _TokenDirectory.from_response(
            await osc.api_request(f"/person/{username or osc.username}/token")
        )
    ).entry


@overload
async def delete_token(osc: Osc, username: str | None = None, *, token: Token) -> None:
    """Delete the supplied token. If no username is specified, then it defaults
    to ``osc.username``.

    """
    ...


@overload
async def delete_token(osc: Osc, username: str | None = None, *, token_id: int) -> None:
    """Delete the token with the specified token_id. If no username is
    specified, then it defaults to ``osc.username``.

    """

    ...


async def delete_token(
    osc: Osc,
    username: str | None = None,
    *,
    token_id: int | None = None,
    token: Token | None = None,
) -> None:
    assert token_id or token
    route = f"/person/{username or osc.username}/token/"
    if token_id:
        route += str(token_id)
    elif token:
        route += str(token.id)
    await osc.api_request(route, method="DELETE")


@overload
async def create_token(
    osc: Osc,
    *,
    project: str,
    package: str,
    operation: Literal[
        TokenKind.REBUILD, TokenKind.RELEASE, TokenKind.RUNSERVICE, None
    ] = None,
    username: str | None = None,
    description: str = "",
) -> Token:
    """Create a package+project scoped token."""
    ...


@overload
async def create_token(
    osc: Osc,
    *,
    operation: Literal[
        TokenKind.REBUILD, TokenKind.RELEASE, TokenKind.RUNSERVICE, None
    ] = None,
    username: str | None = None,
    description: str = "",
) -> Token:
    """Create an un-scoped token."""
    ...


@overload
async def create_token(
    osc: Osc,
    *,
    operation: Literal[TokenKind.WORKFLOW],
    scm_token: str,
    username: str | None = None,
    description: str = "",
) -> Token:
    """Create an un-scoped SCM token."""
    ...


@overload
async def create_token(
    osc: Osc,
    *,
    operation: Literal[TokenKind.WORKFLOW],
    scm_token: str,
    project: str,
    package: str,
    username: str | None = None,
    description: str = "",
) -> Token:
    """Create a package+project scoped SCM token."""
    ...


async def create_token(
    osc: Osc,
    project: str | None = None,
    package: str | None = None,
    operation: TokenKind | None = TokenKind.RUNSERVICE,
    username: str | None = None,
    scm_token: str | None = None,
    description: str = "",
) -> Token:
    """Create a new token for the user with the supplied ``username`` or
    ``osc.username``.

    A service token is created by default.

    """
    if (project and not package) or (not project and package):
        raise ValueError(
            f"The {package=} and {project=} parameter must both be provided"
            " at the same time or not at all"
        )
    if operation == TokenKind.WORKFLOW and not scm_token:
        raise ValueError(
            "The scm_token parameter must be provided for workflow kind tokens"
        )
    if operation == TokenKind.RSS:
        raise ValueError("rss tokens cannot be created via the API")

    params = {
        "project": project,
        "package": package,
        # workaround for https://github.com/openSUSE/open-build-service/issues/15078
        "operation": "runservice" if operation == TokenKind.RUNSERVICE else operation,
        "scm_token": scm_token,
        "description": description,
    }
    kwargs = {k: v for k, v in params.items() if v is not None}

    status = await Status.from_response(
        await osc.api_request(
            f"/person/{username or osc.username}/token/", method="POST", params=kwargs
        )
    )

    if not status.data or "id" not in status.data or len(ids := status.data["id"]) != 1:
        raise ValueError(
            "Invalid status response from OBS, missing or invalid data element"
            " with name='id'"
        )

    id = int(ids[0])
    tokens = await fetch_user_tokens(osc, username)
    for token in tokens:
        if token.id == id:
            return token

    raise RuntimeError("OBS did not return the newly created token")
