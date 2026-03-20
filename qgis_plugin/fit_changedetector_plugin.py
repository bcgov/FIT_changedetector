"""FIT Change Detector QGIS Plugin - Main plugin class."""

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .processing_provider import FITChangeDetectorProvider


class FITChangeDetectorPlugin:
    """Main plugin class, registered with QGIS on startup."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.plugin_dir = os.path.dirname(__file__)

    def initProcessing(self):
        self.provider = FITChangeDetectorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))

        self.action_compare = QAction(icon, "Compare Datasets…", self.iface.mainWindow())
        self.action_compare.setToolTip("Detect changes between two vector datasets")
        self.action_compare.triggered.connect(self._open_compare_dialog)
        self.iface.addPluginToMenu("FIT Change Detector", self.action_compare)
        self.iface.addToolBarIcon(self.action_compare)

        self.action_add_hash = QAction(icon, "Add Hash Key…", self.iface.mainWindow())
        self.action_add_hash.setToolTip("Add a geometry/attribute hash key to a dataset")
        self.action_add_hash.triggered.connect(self._open_add_hash_dialog)
        self.iface.addPluginToMenu("FIT Change Detector", self.action_add_hash)

    def unload(self):
        self.iface.removePluginMenu("FIT Change Detector", self.action_compare)
        self.iface.removePluginMenu("FIT Change Detector", self.action_add_hash)
        self.iface.removeToolBarIcon(self.action_compare)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def _open_compare_dialog(self):
        from .compare_dialog import CompareDialog

        dlg = CompareDialog(self.iface, parent=self.iface.mainWindow())
        dlg.exec_()

    def _open_add_hash_dialog(self):
        from .add_hash_key_dialog import AddHashKeyDialog

        dlg = AddHashKeyDialog(self.iface, parent=self.iface.mainWindow())
        dlg.exec_()
