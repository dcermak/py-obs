from py_obs.osc import Osc
from py_obs.project import Package, Project


async def service_wait(
    osc: Osc, project: Project | str, package: Package | str
) -> None:
    """Wait for all source services for the supplied package in the specified
    project to finish.

    """
    prj_name = project.name if isinstance(project, Project) else project
    pkg_name = package.name if isinstance(package, Package) else package
    # https://api.opensuse.org/apidocs/index#/Sources%20-%20Packages/post_source__project_name___package_name__cmd_waitservice
    await osc.api_request(
        f"/source/{prj_name}/{pkg_name}?cmd=waitservice",
        method="POST",
    )
