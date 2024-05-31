py-obs
======

.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
   :target: https://github.com/astral-sh/ruff
   :alt: Ruff

``py-obs`` is a simple asynchronous python API wrapper for the `Open Build
Service <https://openbuildservice.org/>`_.


Testing
-------

The following commands will launch a local OBS instance using
``docker compose``:

.. code-block:: shell-session

   $ ./start-mini-obs.sh
   $ ./configure-mini-obs.sh

Afterwards, you can run the integration tests agains the local instance via:

.. code-block:: shell-session

   $ poetry run pytest -vv


Recording interactions with build.opensuse.org
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It can be undesirable to setup packages on the local test instance. We use
`pytest-recording <https://github.com/kiwicom/pytest-recording>`_ to record the
HTTP requests against OBS for faster unit tests and for not requiring an account
for testing.

To create a test which runs against `OBS <build.opensuse.org>`_, create a test
function with the following markers:

.. code-block:: python

   @pytest.mark.vcr(filter_headers=["authorization", "openSUSE_session"])
   @pytest.mark.asyncio
   async def test_something_against_obs(osc_from_env: OSC_FROM_ENV_T) -> None:
       async for osc in osc_from_env:
           # now we can do something with osc
           pass

The ``filter_headers`` is **crucial** here, as otherwise you'll record your
password & session.

To record the interaction, run the tests once as follows:

.. code-block:: shell-session

   $ OSC_USER=$my_obs_account OSC_PASSWORD=$my_obs_password \
         poetry run pytest -vv -k something_against_obs

Replace ``something_against_obs`` with the name of your test function (minus the
leading ``test_``) or some other filter, to only run this one test function.

A new cassette file should show up in ``tests/cassettes``. Do not forget to commit
it into git.
