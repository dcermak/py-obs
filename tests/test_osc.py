from datetime import datetime, timedelta
from pathlib import Path
import os.path

import pytest

from py_obs.osc import Osc


def write_oscrc(tmp_path: Path, oscrc_contents: str, monkeypatch) -> None:
    osc = tmp_path / "osc"
    osc.mkdir()
    with open(osc / "oscrc", "w") as oscrc_f:
        oscrc_f.write(oscrc_contents)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


@pytest.mark.parametrize(
    "oscrc,username,password,ssh_key_path,apiurl,apiurl_param",
    [
        (
            """[general]
apiurl = https://api.foo.bar

[https://api.foo.bar]
user = me
pass = secret
""",
            "me",
            "secret",
            None,
            "https://api.foo.bar",
            None,
        ),
        (
            """[general]
apiurl = https://api.foo.baz

[https://api.foo.baz]
user = else
sshkey = id_ed22519
""",
            "else",
            "",
            os.path.expanduser("~/.ssh/id_ed22519.pub"),
            "https://api.foo.baz",
            None,
        ),
        (
            """[general]
apiurl = https://api.foo.baz

[https://api.foo.baz]
[https://api.bar.foo]
user = else
sshkey = id_ed22519
""",
            "else",
            "",
            os.path.expanduser("~/.ssh/id_ed22519.pub"),
            "https://api.bar.foo",
            "https://api.bar.foo",
        ),
    ],
)
def test_read_from_oscrc(
    tmp_path: Path,
    oscrc: str,
    monkeypatch,
    username: str,
    password: str | None,
    ssh_key_path: str | None,
    apiurl: str,
    apiurl_param: str | None,
) -> None:
    write_oscrc(tmp_path, oscrc, monkeypatch)
    osc = Osc.from_oscrc(api_url=apiurl_param)

    assert osc.username == username
    assert osc.password == password
    assert osc.ssh_key_path == ssh_key_path
    assert apiurl == osc.api_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "oscrc,err_msg",
    [
        (
            """[general]
""",
            "oscrc general section is missing the apiurl option",
        ),
        (
            """[general]
apiurl = https://api.foo.baz

[https://api.foo]
""",
            "Missing section 'https://api.foo.baz' in oscrc",
        ),
        (
            """[general]
apiurl = https://api.foo.baz

[https://api.foo.baz]
""",
            "user option missing in section 'https://api.foo.baz'",
        ),
        (
            """[general]
apiurl = https://api.foo.baz

[https://api.foo.baz]
user=me
""",
            "pass and sshkey are both missing in section 'https://api.foo.baz'",
        ),
    ],
)
async def test_read_from_oscrc_error(
    tmp_path: Path,
    oscrc: str,
    monkeypatch,
    err_msg: str,
) -> None:
    write_oscrc(tmp_path, oscrc, monkeypatch)
    with pytest.raises(ValueError) as val_err_ctx:
        Osc.from_oscrc()

    assert err_msg in str(val_err_ctx)


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_backoff() -> None:
    """Test the exponential back-off in Osc.api_request.

    We handcraft a vcr cassette that has four error requests with errors 500,
    502, 503 and 504. api_request should retry the request up to five times with
    exponentially increasing times.

    """
    before = datetime.now()
    resp = await Osc("foo", password="irrelevant").api_request("/test")
    after = datetime.now()

    # we have 4 errors, i.e. we wait for at least (1 + 2 + 4 + 8)s = 15
    assert after - before >= timedelta(seconds=15)

    # final message is a 200
    assert resp.status == 200
    assert (await resp.text()) == "Success"
