import xml.etree.ElementTree as ET
import pytest
from py_obs.project import DevelProject, Package, Person
from py_obs.xml_factory import StrElementField


@pytest.mark.parametrize(
    "package,prj_meta",
    [
        (
            Package(
                name="buildah",
                title=StrElementField(
                    "A tool which facilitates building OCI container images"
                ),
                description=StrElementField(
                    "Buildah provides a command line tool which can be used to"
                ),
                scmsync=StrElementField(
                    "https://github.com/containers/buildah?subdir=dist"
                ),
                devel=DevelProject(project="devel:microos", package="buildah"),
            ),
            """<package name="buildah"><title>A tool which facilitates building OCI container images</title><description>Buildah provides a command line tool which can be used to</description><scmsync>https://github.com/containers/buildah?subdir=dist</scmsync><devel project="devel:microos" package="buildah"/></package>""",
        ),
        (
            Package(
                name="python-podman",
                title=StrElementField("A library to interact with a Podman server"),
                description=StrElementField(
                    "A library to interact with a Podman server"
                ),
                person=[Person(userid="dancermak")],
                url=StrElementField("https://github.com/containers/podman-py"),
            ),
            """<package name="python-podman"><title>A library to interact with a Podman server</title><description>A library to interact with a Podman server</description><person userid="dancermak" role="maintainer"/><url>https://github.com/containers/podman-py</url></package>""",
        ),
    ],
)
def test_package_meta(package: Package, prj_meta: str):
    assert ET.canonicalize(
        ET.tostring(package.meta, short_empty_elements=True).decode("utf-8")
    ) == ET.canonicalize(prj_meta)
