from dataclasses import dataclass
from typing import ClassVar

from py_obs.osc import Osc
from py_obs.xml_factory import MetaMixin
from py_obs.xml_factory import StrElementField


@dataclass(frozen=True)
class Configuration(MetaMixin):
    """Configuration of the OBS instance"""

    _element_name: ClassVar[str] = "configuration"

    #: title of the instance
    title: StrElementField
    #: name of the instance
    name: StrElementField
    #: url to the webui
    obs_url: StrElementField | None


async def fetch_configuration(osc: Osc) -> Configuration:
    """Fetch the configuration of the OBS instance"""
    return await Configuration.from_response(await osc.api_request("/configuration"))
