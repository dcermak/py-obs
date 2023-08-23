from dataclasses import dataclass, field
from typing import ClassVar, Type
import xml.etree.ElementTree as ET

from py_obs.xml_factory import MetaMixin, StrElementField


@dataclass(frozen=True)
class Status(MetaMixin):
    """Generic status response from OBS"""

    _element_name: ClassVar[str] = "status"

    #: code field indicating the overall status
    code: str
    summary: StrElementField | None = None
    details: StrElementField | None = None

    #: arbitrary data returned by OBS
    data: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_xml(cls: Type["Status"], xml: ET.Element | str | bytes) -> "Status":
        xml_element = ET.fromstring(xml) if isinstance(xml, (str, bytes)) else xml
        summary = None
        details = None
        data: dict[str, list[str]] = {}

        if (
            summary_elem := xml_element.find("summary")
        ) is not None and summary_elem.text:
            summary = StrElementField(summary_elem.text)

        if (
            details_elem := xml_element.find("details")
        ) is not None and details_elem.text:
            details = StrElementField(details_elem.text)

        for data_elem in xml_element.findall("data"):
            if not data_elem.text:
                continue

            if "name" in data_elem.attrib:
                if (name := data_elem.attrib["name"]) in data:
                    data[name].append(data_elem.text)
                else:
                    data[name] = [data_elem.text]

        return Status(
            code=xml_element.attrib["code"], summary=summary, details=details, data=data
        )
