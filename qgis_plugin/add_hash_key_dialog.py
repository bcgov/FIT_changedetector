"""Add Hash Key dialog - GUI wrapper for 'changedetector add-hash-key' command."""

import os

from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .utils import (
    check_fit_changedetector,
    run_add_hash_key_via_cli,
    run_add_hash_key_via_library,
)

PRECISIONS = [1, 0.1, 0.01, 0.001, 0.0001, 0.00001, 0.000001, 0.0000001, 0.00000001]


class AddHashWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, mode, params, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.params = params

    def run(self):
        try:
            self.log.emit("Adding hash key…")
            if self.mode == "library":
                run_add_hash_key_via_library(self.params)
            else:
                result = run_add_hash_key_via_cli(self.params)
                if result.stdout:
                    self.log.emit(result.stdout)
                if result.stderr:
                    self.log.emit(result.stderr)
                if result.returncode != 0:
                    self.error.emit(f"CLI returned exit code {result.returncode}:\n{result.stderr}")
                    return
            self.finished.emit(self.params["out_file"])
        except Exception as e:
            self.error.emit(str(e))


class AddHashKeyDialog(QDialog):
    """Dialog for the 'add-hash-key' command."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.worker = None
        self._mode, self._version = check_fit_changedetector()

        self.setWindowTitle("FIT Change Detector – Add Hash Key")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Availability banner
        banner = QLabel()
        if self._mode == "library":
            banner.setText(f"fit_changedetector {self._version} (library mode)")
            banner.setStyleSheet("color: green; font-weight: bold;")
        elif self._mode == "cli":
            banner.setText(f"changedetector {self._version} CLI (subprocess mode)")
            banner.setStyleSheet("color: orange; font-weight: bold;")
        else:
            banner.setText("fit_changedetector is NOT installed.")
            banner.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(banner)

        form = QFormLayout()
        layout.addLayout(form)

        # Input file
        self.in_file = QLineEdit()
        btn_in = QPushButton("Browse…")
        btn_in.clicked.connect(lambda: self._browse_file(self.in_file))
        row_in = QHBoxLayout()
        row_in.addWidget(self.in_file)
        row_in.addWidget(btn_in)
        form.addRow("Input file:", row_in)

        self.in_layer = QLineEdit()
        self.in_layer.setPlaceholderText("(optional)")
        form.addRow("Input layer:", self.in_layer)

        # Output file
        self.out_file = QLineEdit()
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(self._browse_out_file)
        row_out = QHBoxLayout()
        row_out.addWidget(self.out_file)
        row_out.addWidget(btn_out)
        form.addRow("Output file (.gdb):", row_out)

        self.out_layer = QLineEdit()
        self.out_layer.setPlaceholderText("(defaults to input layer name)")
        form.addRow("Output layer:", self.out_layer)

        # Options
        self.hash_key = QLineEdit("fcd_hash_id")
        form.addRow("Hash key column name:", self.hash_key)

        self.hash_fields = QLineEdit()
        self.hash_fields.setPlaceholderText("Comma-separated fields to include in hash")
        form.addRow("Hash fields:", self.hash_fields)

        self.precision = QComboBox()
        for p in PRECISIONS:
            self.precision.addItem(str(p), p)
        self.precision.setCurrentIndex(2)  # default 0.01
        form.addRow("Coordinate precision:", self.precision)

        self.crs = QLineEdit()
        self.crs.setPlaceholderText("e.g. EPSG:3005  (optional)")
        form.addRow("CRS (reproject to):", self.crs)

        self.drop_null_geometry = QCheckBox("Drop records with null geometry")
        form.addRow(self.drop_null_geometry)

        # Log
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(100)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.log_output)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Buttons
        self.button_box = QDialogButtonBox()
        self.run_btn = self.button_box.addButton("Run", QDialogButtonBox.AcceptRole)
        self.close_btn = self.button_box.addButton("Close", QDialogButtonBox.RejectRole)
        self.run_btn.clicked.connect(self._run)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(self.button_box)

    def _browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select input file",
            "",
            "Supported files (*.shp *.gpkg *.geojson);;All files (*)",
        )
        if path:
            line_edit.setText(path)

    def _browse_out_file(self):
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            self.out_file.setText(os.path.join(path, "output_with_hash.gdb"))

    def _run(self):
        if self._mode == "unavailable":
            QMessageBox.critical(self, "Not available", "fit_changedetector is not installed.")
            return

        in_file = self.in_file.text().strip()
        out_file = self.out_file.text().strip()
        if not in_file or not out_file:
            QMessageBox.warning(self, "Missing inputs", "Please select input and output files.")
            return

        params = {
            "in_file": in_file,
            "in_layer": self.in_layer.text().strip() or None,
            "out_file": out_file,
            "out_layer": self.out_layer.text().strip() or None,
            "hash_key": self.hash_key.text().strip() or "fcd_hash_id",
            "hash_fields": self.hash_fields.text().strip(),
            "precision": self.precision.currentData(),
            "crs": self.crs.text().strip() or None,
            "drop_null_geometry": self.drop_null_geometry.isChecked(),
        }

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.log_output.clear()

        self.worker = AddHashWorker(self._mode, params, parent=self)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.log.connect(self.log_output.append)
        self.worker.start()

    def _on_finished(self, out_file):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.log_output.append(f"Done! Output: {out_file}")
        QMessageBox.information(self, "Complete", f"Hash key added.\nOutput: {out_file}")

    def _on_error(self, message):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.log_output.append(f"ERROR: {message}")
        QMessageBox.critical(self, "Error", message)
