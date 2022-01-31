import sys
import tempfile
from pathlib import Path

import substra
import substratools

import connectlib
from connectlib.remote import register

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"


def test_local_lib_install_command(session_dir):
    # Test that editable wheel are generated
    libs = [connectlib, substra, substratools]
    operation_dir = Path(tempfile.mkdtemp(dir=session_dir.as_posix()))

    _ = register.local_lib_install_command(
        lib_modules=libs,
        operation_dir=operation_dir,
        python_major_minor=PYTHON_VERSION,
    )

    wheels_created = []

    for lib in libs:
        wheels_created.append(
            (operation_dir / f"connectlib_internal/dist/{lib.__name__}-{lib.__version__}-py3-none-any.whl").exists()
        )

    assert all(wheels_created)


def test_pypi_lib_install_command(session_dir):
    # Test that pypi wheel can be downloaded
    libs = [connectlib, substra, substratools]
    operation_dir = Path(tempfile.mkdtemp(dir=session_dir.as_posix()))

    # We check that we have access to the pypi repo not the specific packages version otherwise this test will fail
    # when trying to creates a new version of connectlib as the running dev version on the ci and on a local computer
    # (0.x.0) won't have been released yet (it is not in owkin pypi).

    # save the current versions the libs to set them back later
    connectlib_version = connectlib.__version__
    connectlib.__version__ = "0.5.0"

    substra_version = substra.__version__
    substra.__version__ = "0.14.0"

    substratools_version = substratools.__version__
    substratools.__version__ = "0.9.1"

    _ = register.pypi_lib_install_command(
        lib_modules=libs, python_major_minor=PYTHON_VERSION, operation_dir=operation_dir
    )

    wheels_created = []

    for lib in libs:
        wheels_created.append(
            (Path().home() / f".connectlib/{lib.__name__}-{lib.__version__}-py3-none-any.whl").exists()
        )

    connectlib.__version__ = connectlib_version
    substra.__version__ = substra_version
    substratools.__version__ = substratools_version

    assert all(wheels_created)
