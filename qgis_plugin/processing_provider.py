"""QGIS Processing Framework provider for FIT Change Detector algorithms.

Registering algorithms here makes them available in:
  - Processing Toolbox
  - Graphical Modeler
  - Python console via processing.run(...)
  - QGIS batch mode / command line
"""

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms import AddHashKeyAlgorithm, CompareAlgorithm


class FITChangeDetectorProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(CompareAlgorithm())
        self.addAlgorithm(AddHashKeyAlgorithm())

    def id(self):
        return "fit_changedetector"

    def name(self):
        return "FIT Change Detector"

    def longName(self):
        return "FIT Change Detector (bcgov)"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return super().icon()
