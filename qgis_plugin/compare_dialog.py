"""Compare dialog - GUI wrapper for 'changedetector compare' command."""

import os
from datetime import datetime

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .utils import (
    check_fit_changedetector,
    run_compare_via_cli,
    run_compare_via_library,
)

PRECISIONS = [1, 0.1, 0.01, 0.001, 0.0001, 0.00001, 0.000001, 0.0000001, 0.00000001]


class CompareWorker(QThread):
    """Background worker thread for running the comparison."""

    finished = pyqtSignal(str)  # emits out_file path on success
    error = pyqtSignal(str)  # emits error message on failure
    log = pyqtSignal(str)  # emits log messages during processing

    def __init__(self, mode, params, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.params = params

    def run(self):
        try:
            self.log.emit("Starting comparison...")
            if self.mode == "library":
                run_compare_via_library(self.params)
            else:
                result = run_compare_via_cli(self.params)
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


class CompareDialog(QDialog):
    """Dialog for the 'compare' command."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.worker = None

        self.setWindowTitle("FIT Change Detector – Compare Datasets")
        self.setMinimumWidth(600)

        self._check_availability()
        self._build_ui()

    def _check_availability(self):
        self._mode, self._version = check_fit_changedetector()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Availability banner
        banner = QLabel()
        if self._mode == "library":
            banner.setText(f"fit_changedetector {self._version} (library mode)")
            banner.setStyleSheet("color: green; font-weight: bold;")
        elif self._mode == "cli":
            banner.setText(f"changedetector CLI {self._version} (subprocess mode)")
            banner.setStyleSheet("color: orange; font-weight: bold;")
        else:
            banner.setText("fit_changedetector is NOT installed. Install it before running.")
            banner.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(banner)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Inputs ──────────────────────────────────────────────────
        tab_inputs = QWidget()
        form_inputs = QFormLayout(tab_inputs)

        # Dataset A
        grp_a = QGroupBox("Dataset A (original)")
        form_a = QFormLayout(grp_a)

        self.file_a = QLineEdit()
        btn_a = QPushButton("Browse…")
        btn_a.clicked.connect(lambda: self._browse_file(self.file_a))
        row_a = QHBoxLayout()
        row_a.addWidget(self.file_a)
        row_a.addWidget(btn_a)
        form_a.addRow("File / GDB:", row_a)

        self.layer_a = QLineEdit()
        self.layer_a.setPlaceholderText("(optional – layer name within file)")
        form_a.addRow("Layer:", self.layer_a)
        form_inputs.addRow(grp_a)

        # Dataset B
        grp_b = QGroupBox("Dataset B (new)")
        form_b = QFormLayout(grp_b)

        self.file_b = QLineEdit()
        btn_b = QPushButton("Browse…")
        btn_b.clicked.connect(lambda: self._browse_file(self.file_b))
        row_b = QHBoxLayout()
        row_b.addWidget(self.file_b)
        row_b.addWidget(btn_b)
        form_b.addRow("File / GDB:", row_b)

        self.layer_b = QLineEdit()
        self.layer_b.setPlaceholderText("(optional – layer name within file)")
        form_b.addRow("Layer:", self.layer_b)
        form_inputs.addRow(grp_b)

        # Output
        grp_out = QGroupBox("Output")
        form_out = QFormLayout(grp_out)

        self.out_file = QLineEdit()
        self.out_file.setPlaceholderText("Default: changedetector_YYYYMMDD_HHMM.gdb")
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(self._browse_out_file)
        row_out = QHBoxLayout()
        row_out.addWidget(self.out_file)
        row_out.addWidget(btn_out)
        form_out.addRow("Output .gdb:", row_out)
        form_inputs.addRow(grp_out)

        tabs.addTab(tab_inputs, "Inputs / Output")

        # ── Tab 2: Keys & Fields ───────────────────────────────────────────
        tab_fields = QWidget()
        form_fields = QFormLayout(tab_fields)

        self.primary_key = QLineEdit()
        self.primary_key.setPlaceholderText("e.g. park_id  (leave blank to hash geometry)")
        form_fields.addRow("Primary key:", self.primary_key)

        self.fields = QLineEdit()
        self.fields.setPlaceholderText("Comma-separated field names (blank = all common)")
        form_fields.addRow("Include fields:", self.fields)

        self.ignore_fields = QLineEdit()
        self.ignore_fields.setPlaceholderText("Comma-separated field names to ignore")
        form_fields.addRow("Ignore fields:", self.ignore_fields)

        self.hash_key = QLineEdit("fcd_hash_id")
        form_fields.addRow("Hash key column name:", self.hash_key)

        self.hash_fields = QLineEdit()
        self.hash_fields.setPlaceholderText(
            "Extra fields to include in geometry hash (comma-separated)"
        )
        form_fields.addRow("Hash fields:", self.hash_fields)

        tabs.addTab(tab_fields, "Keys & Fields")

        # ── Tab 3: Options ─────────────────────────────────────────────────
        tab_opts = QWidget()
        form_opts = QFormLayout(tab_opts)

        self.precision = QComboBox()
        for p in PRECISIONS:
            self.precision.addItem(str(p), p)
        self.precision.setCurrentIndex(2)  # default 0.01
        form_opts.addRow("Coordinate precision:", self.precision)

        self.crs = QLineEdit()
        self.crs.setPlaceholderText("e.g. EPSG:3005  (optional reproject)")
        form_opts.addRow("CRS:", self.crs)

        self.suffix_a = QLineEdit("original")
        form_opts.addRow("Suffix A:", self.suffix_a)

        self.suffix_b = QLineEdit("new")
        form_opts.addRow("Suffix B:", self.suffix_b)

        self.drop_null_geometry = QCheckBox("Drop records with null geometry")
        form_opts.addRow(self.drop_null_geometry)

        self.dump_inputs = QCheckBox("Write source datasets (with hash key) to output .gdb")
        form_opts.addRow(self.dump_inputs)

        self.load_results = QCheckBox("Load result layers into QGIS on completion")
        self.load_results.setChecked(True)
        form_opts.addRow(self.load_results)

        tabs.addTab(tab_opts, "Options")

        # ── Log ───────────────────────────────────────────────────────────
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(120)
        self.log_output.setPlaceholderText("Log output will appear here…")
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.log_output)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Buttons
        self.button_box = QDialogButtonBox()
        self.run_btn = self.button_box.addButton("Run", QDialogButtonBox.AcceptRole)
        self.close_btn = self.button_box.addButton("Close", QDialogButtonBox.RejectRole)
        self.run_btn.clicked.connect(self._run)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(self.button_box)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _browse_file(self, line_edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select dataset",
            "",
            "Supported files (*.shp *.gpkg *.geojson *.gdb);;All files (*)",
        )
        if path:
            line_edit.setText(path)

    def _browse_out_file(self):
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            self.out_file.setText(os.path.join(path, f"changedetector_{ts}.gdb"))

    def _run(self):
        if self._mode == "unavailable":
            QMessageBox.critical(
                self,
                "Not available",
                "fit_changedetector is not installed.\n\n"
                "Install it with:\n  pip install fit_changedetector",
            )
            return

        file_a = self.file_a.text().strip()
        file_b = self.file_b.text().strip()
        if not file_a or not file_b:
            QMessageBox.warning(self, "Missing inputs", "Please select both input files.")
            return

        params = {
            "file_a": file_a,
            "file_b": file_b,
            "layer_a": self.layer_a.text().strip() or None,
            "layer_b": self.layer_b.text().strip() or None,
            "out_file": self.out_file.text().strip() or None,
            "primary_key": self.primary_key.text().strip(),
            "fields": self.fields.text().strip(),
            "ignore_fields": self.ignore_fields.text().strip(),
            "hash_key": self.hash_key.text().strip() or "fcd_hash_id",
            "hash_fields": self.hash_fields.text().strip(),
            "precision": self.precision.currentData(),
            "suffix_a": self.suffix_a.text().strip() or "original",
            "suffix_b": self.suffix_b.text().strip() or "new",
            "drop_null_geometry": self.drop_null_geometry.isChecked(),
            "dump_inputs": self.dump_inputs.isChecked(),
            "crs": self.crs.text().strip() or None,
        }

        if not params["out_file"]:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            params["out_file"] = f"changedetector_{ts}.gdb"

        self._set_running(True)
        self.log_output.clear()

        self.worker = CompareWorker(self._mode, params, parent=self)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.log.connect(self.log_output.append)
        self.worker.start()

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.progress.setVisible(running)

    def _on_finished(self, out_file: str):
        self._set_running(False)
        self.log_output.append(f"Done! Output: {out_file}")

        if self.load_results.isChecked() and os.path.exists(out_file):
            self._load_result_layers(out_file)

        QMessageBox.information(
            self,
            "Complete",
            f"Change detection complete.\nOutput written to:\n{out_file}",
        )

    def _on_error(self, message: str):
        self._set_running(False)
        self.log_output.append(f"ERROR: {message}")
        QMessageBox.critical(self, "Error", message)

    def _load_result_layers(self, gdb_path: str):
        """Load each output layer from the result .gdb into QGIS."""
        layer_names = ["NEW", "DELETED", "MODIFIED_BOTH", "MODIFIED_ATTR", "MODIFIED_GEOM"]
        colour_map = {
            "NEW": "0,200,0,200",
            "DELETED": "200,0,0,200",
            "MODIFIED_BOTH": "255,165,0,200",
            "MODIFIED_ATTR": "0,0,255,200",
            "MODIFIED_GEOM": "128,0,128,200",
        }
        for name in layer_names:
            uri = f"{gdb_path}|layername={name}"
            lyr = QgsVectorLayer(uri, f"FCD_{name}", "ogr")
            if lyr.isValid() and lyr.featureCount() > 0:
                # apply a basic colour
                colour = colour_map.get(name, "128,128,128,200")
                lyr.setCustomProperty("fcd_colour", colour)
                QgsProject.instance().addMapLayer(lyr)
