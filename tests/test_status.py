import pytest
from py_obs.status import Status


@pytest.mark.parametrize(
    "status,xml",
    [
        (
            Status(
                code="ok",
                summary="Ok",
                details="Operation successfull.",
                data={"targetproject": ["home:kfreitag:Factory"]},
            ),
            """<?xml version="1.0" encoding="UTF-8"?>
<status code="ok">
  <summary>Ok</summary>
  <details>Operation successfull.</details>
  <data name="targetproject">home:kfreitag:Factory</data>
</status>""",
        ),
        (Status(code="foo"), """<status code='foo'></status>"""),
        (
            Status(
                code="ok",
                data={
                    "targetproject": ["home:me:Factory"],
                    "destproject": ["openSUSE:Factory"],
                    "req_id": ["15", "42"],
                },
            ),
            """<?xml version="1.0" encoding="UTF-8"?>
<status code="ok">
  <data name="targetproject">home:me:Factory</data>
  <data name="destproject">openSUSE:Factory</data>
  <data name="req_id">15</data>
  <data name="req_id">42</data>
</status>""",
        ),
    ],
)
def test_status_from_xml(status: Status, xml: str) -> None:
    assert Status.from_xml(xml) == status
