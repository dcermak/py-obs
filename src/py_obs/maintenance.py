from dataclasses import dataclass

from aiohttp import ClientResponse
from aiohttp import ClientResponseError

from py_obs.osc import ObsException
from py_obs.osc import Osc
from py_obs.project import Package
from py_obs.status import Status
from py_obs.xml_factory import MetaMixin


@dataclass(frozen=True)
class _Collection(MetaMixin):
    _element_name = "collection"

    @dataclass(frozen=True)
    class _Package(MetaMixin):
        _element_name = "package"

        package: str
        project: str

    package: list[_Package]


class DoubleBranchException(ObsException):
    """Exception raised when a package is branched twice into the user's home
    project.

    """


async def _mbranch(
    osc: Osc, pkg: Package | str, dry_run: bool = False, raise_for_status: bool = False
) -> ClientResponse:
    params = {
        "cmd": "branch",
        "attribute": "OBS:Maintained",
        "package": pkg if isinstance(pkg, str) else pkg.name,
        "update_project_attribute": "OBS:UpdateProject",
    }
    if dry_run:
        params["dryrun"] = "1"

    return await osc.api_request(
        "/source", method="POST", raise_for_status=raise_for_status, params=params
    )


async def mbranch(osc: Osc, pkg: Package | str) -> str:
    """Creates a maintenance branch for every maintained code stream of the
    package in your home project.

    Returns:

    The name of the project into which the package has been branched

    """
    resp = await _mbranch(osc, pkg, raise_for_status=False, dry_run=False)

    if resp.status == 404:
        # package not found -> not maintained anywhere
        raise ValueError(
            f"Package {pkg if isinstance(pkg, str) else pkg.name} cannot be maintenance branched: package not found"
        ) from ClientResponseError(
            request_info=resp.request_info, history=resp.history, status=resp.status
        )

    if resp.status == 400:
        # try to obtain the status from the response in case this is a double branch
        try:
            status = Status.from_xml(await resp.read())
            if status.code == "double_branch_package":
                raise DoubleBranchException(
                    request_info=resp.request_info,
                    history=resp.history,
                    status=resp.status,
                    message=str(status.summary) if status.summary else "",
                )
        except ValueError:
            # this was not a OBS status response or not a double branch
            # => just give up
            resp.raise_for_status()

    resp.raise_for_status()

    status = await Status.from_response(resp)
    return status.data["targetproject"][0]


async def fetch_maintained_code_streams(osc: Osc, pkg: Package | str) -> list[str]:
    """Fetches the list of code streams where the specified package is
    maintained (and not just inherited from). If the package does not exist,
    then an empty list is returned.

    """
    resp = await _mbranch(osc, pkg, raise_for_status=False, dry_run=True)
    if resp.status == 404:
        return []
    resp.raise_for_status()

    res = await _Collection.from_response(resp)
    return [pkg.project for pkg in res.package]
