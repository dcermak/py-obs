from dataclasses import dataclass
from py_obs.osc import ObsException, Osc
from py_obs.project import Package
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


async def fetch_maintained_code_streams(osc: Osc, pkg: Package | str) -> list[str]:
    """Fetches the list of code streams where the specified package is
    maintained (and not just inherited from). If the package does not exist,
    then an empty list is returned.

    """
    try:
        resp = await osc.api_request(
            "/source",
            method="POST",
            params={
                "cmd": "branch",
                "dryrun": "1",
                "attribute": "OBS:Maintained",
                "package": pkg if isinstance(pkg, str) else pkg.name,
                "update_project_attribute": "OBS:UpdateProject",
            },
        )
    except ObsException as obs_err:
        # package not found -> not maintained anywhere
        if obs_err.status == 404:
            return []
        raise

    res = await _Collection.from_response(resp)
    return [pkg.project for pkg in res.package]
