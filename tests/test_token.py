import pytest
from py_obs.token import TokenKind, create_token, delete_token, fetch_user_tokens

from tests.conftest import HOME_PROJ_T, osc_test_user_name

# hack, rely on implementation details of the home_project fixture
PRJ = f"home:{osc_test_user_name()}"
PKG = "emacs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    # skip rss tokens, they cannot be created via the API:
    # https://github.com/openSUSE/open-build-service/issues/14810
    [
        TokenKind.RUNSERVICE,
        TokenKind.REBUILD,
        TokenKind.RELEASE,
        None,
        TokenKind.WORKFLOW,
    ],
)
@pytest.mark.parametrize("project,package", [(None, None), (PRJ, PKG)])
@pytest.mark.parametrize("description", ["", "this is a description"])
async def test_token_operations(
    home_project: HOME_PROJ_T,
    kind: TokenKind | None,
    description: str,
    project: str | None,
    package: str | None,
) -> None:
    async for osc, admin_osc, _, _ in home_project:
        # wipe all tokens before the test to ensure nothing can interfere
        for token in await fetch_user_tokens(osc):
            await delete_token(admin_osc, username=osc.username, token=token)

        kwargs = {"scm_token": "foobar"} if kind == TokenKind.WORKFLOW else {}
        token = await create_token(
            osc,
            operation=kind,
            description=description,
            project=project,
            package=package,
            **kwargs,
        )

        assert token.kind == (kind or TokenKind.RUNSERVICE)
        assert token.description == description
        assert token.package == package
        assert token.project == project

        assert token in await fetch_user_tokens(osc)

        await delete_token(admin_osc, username=osc.username, token=token)
        assert token not in await fetch_user_tokens(osc)
