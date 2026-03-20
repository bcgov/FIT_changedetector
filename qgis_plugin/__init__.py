"""FIT Change Detector QGIS Plugin

Entry point for QGIS plugin loader.
"""


def classFactory(iface):
    """Load the FITChangeDetectorPlugin class.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .fit_changedetector_plugin import FITChangeDetectorPlugin

    return FITChangeDetectorPlugin(iface)
