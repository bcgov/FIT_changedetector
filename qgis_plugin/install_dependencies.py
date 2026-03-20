"""Install fit_changedetector into the QGIS Python environment.

Run this script from the QGIS Python console to install the dependency:

    exec(open('/path/to/install_dependencies.py').read())

Or use the Plugin Manager → Install from ZIP after packaging with `make zip`.
"""

import subprocess
import sys


def install():
    """Install fit_changedetector using the QGIS Python pip."""
    pkg = "fit_changedetector"
    print(f"Installing {pkg} into QGIS Python environment...")
    print(f"Python: {sys.executable}")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"Successfully installed {pkg}")
        print(result.stdout)
    else:
        print(f"Failed to install {pkg}")
        print(result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    install()
