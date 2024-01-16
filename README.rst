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
``docker-compose``:

.. code-block:: shell-session

   ./start-mini-obs.sh
   ./configure-mini-obs.sh
