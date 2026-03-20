"""QGIS Processing algorithms for fit_changedetector.

These algorithms integrate with the Processing Framework, enabling:
  - Use in the graphical modeler
  - Batch processing
  - Scripting via processing.run()
  - Integration with QGIS Server processing capabilities

Example (QGIS Python console):
    import processing
    result = processing.run(
        "fit_changedetector:compare",
        {
            'FILE_A': '/data/parks_2023.gpkg',
            'FILE_B': '/data/parks_2024.gpkg',
            'PRIMARY_KEY': 'park_id',
            'OUTPUT': '/tmp/changes.gdb',
        }
    )
"""

import os
from datetime import datetime

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication

PRECISIONS = [1.0, 0.1, 0.01, 0.001, 0.0001, 0.00001, 0.000001, 0.0000001, 0.00000001]
PRECISION_LABELS = [str(p) for p in PRECISIONS]


class CompareAlgorithm(QgsProcessingAlgorithm):
    """Detect changes between two geospatial datasets.

    Equivalent to: changedetector compare <file_a> <file_b> [options]
    """

    FILE_A = "FILE_A"
    LAYER_A = "LAYER_A"
    FILE_B = "FILE_B"
    LAYER_B = "LAYER_B"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    PRIMARY_KEY = "PRIMARY_KEY"
    FIELDS = "FIELDS"
    IGNORE_FIELDS = "IGNORE_FIELDS"
    HASH_KEY = "HASH_KEY"
    HASH_FIELDS = "HASH_FIELDS"
    PRECISION = "PRECISION"
    CRS = "CRS"
    SUFFIX_A = "SUFFIX_A"
    SUFFIX_B = "SUFFIX_B"
    DROP_NULL_GEOMETRY = "DROP_NULL_GEOMETRY"
    DUMP_INPUTS = "DUMP_INPUTS"

    OUTPUT_NEW = "OUTPUT_NEW"
    OUTPUT_DELETED = "OUTPUT_DELETED"
    OUTPUT_MODIFIED_BOTH = "OUTPUT_MODIFIED_BOTH"
    OUTPUT_MODIFIED_ATTR = "OUTPUT_MODIFIED_ATTR"
    OUTPUT_MODIFIED_GEOM = "OUTPUT_MODIFIED_GEOM"

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return CompareAlgorithm()

    def name(self):
        return "compare"

    def displayName(self):
        return self.tr("Compare Datasets")

    def group(self):
        return self.tr("Change Detection")

    def groupId(self):
        return "changedetection"

    def shortHelpString(self):
        return self.tr(
            "Compare two geospatial datasets and classify features as:\n"
            "  NEW, DELETED, UNCHANGED, MODIFIED_ATTR, MODIFIED_GEOM, MODIFIED_BOTH\n\n"
            "If no primary key is provided, a geometry-based hash key is computed automatically.\n\n"
            "Requires the fit_changedetector package (or CLI) to be installed."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.FILE_A,
                self.tr("Dataset A (original)"),
                behavior=QgsProcessingParameterFile.File,
                fileFilter="Spatial files (*.shp *.gpkg *.geojson *.gdb);;All files (*)",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.LAYER_A,
                self.tr("Layer name within Dataset A"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.FILE_B,
                self.tr("Dataset B (new)"),
                behavior=QgsProcessingParameterFile.File,
                fileFilter="Spatial files (*.shp *.gpkg *.geojson *.gdb);;All files (*)",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.LAYER_B,
                self.tr("Layer name within Dataset B"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output folder (a timestamped .gdb will be created here)"),
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.PRIMARY_KEY,
                self.tr("Primary key column (leave blank to auto-hash geometry)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.FIELDS,
                self.tr("Fields to compare (comma-separated; blank = all common fields)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.IGNORE_FIELDS,
                self.tr("Fields to ignore (comma-separated)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.HASH_KEY,
                self.tr("Hash key column name"),
                defaultValue="fcd_hash_id",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.HASH_FIELDS,
                self.tr("Extra fields to include in geometry hash (comma-separated)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PRECISION,
                self.tr("Coordinate precision"),
                options=PRECISION_LABELS,
                defaultValue=2,  # index of 0.01
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.CRS,
                self.tr("Reproject to CRS (e.g. EPSG:3005; leave blank to keep original)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.SUFFIX_A,
                self.tr("Column suffix for Dataset A values in diff output"),
                defaultValue="original",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.SUFFIX_B,
                self.tr("Column suffix for Dataset B values in diff output"),
                defaultValue="new",
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DROP_NULL_GEOMETRY,
                self.tr("Drop records with null geometry"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DUMP_INPUTS,
                self.tr("Write source datasets (with hash key) to output .gdb"),
                defaultValue=False,
            )
        )

        # Outputs – one per change category
        for output_id, label in [
            (self.OUTPUT_NEW, "NEW features"),
            (self.OUTPUT_DELETED, "DELETED features"),
            (self.OUTPUT_MODIFIED_BOTH, "MODIFIED_BOTH (attribute + geometry changes)"),
            (self.OUTPUT_MODIFIED_ATTR, "MODIFIED_ATTR (attribute-only changes)"),
            (self.OUTPUT_MODIFIED_GEOM, "MODIFIED_GEOM (geometry-only changes)"),
        ]:
            self.addOutput(QgsProcessingOutputVectorLayer(output_id, self.tr(label)))

    def processAlgorithm(self, parameters, context, feedback):
        from .utils import (
            check_fit_changedetector,
            run_compare_via_cli,
            run_compare_via_library,
        )

        mode, _ = check_fit_changedetector()
        if mode == "unavailable":
            raise QgsProcessingException(
                "fit_changedetector is not installed. " "Run: pip install fit_changedetector"
            )

        file_a = self.parameterAsFile(parameters, self.FILE_A, context)
        file_b = self.parameterAsFile(parameters, self.FILE_B, context)
        out_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        out_file = os.path.join(out_folder, f"changedetector_{ts}.gdb")

        precision_idx = self.parameterAsEnum(parameters, self.PRECISION, context)
        precision = PRECISIONS[precision_idx]

        params = {
            "file_a": file_a,
            "file_b": file_b,
            "layer_a": self.parameterAsString(parameters, self.LAYER_A, context) or None,
            "layer_b": self.parameterAsString(parameters, self.LAYER_B, context) or None,
            "out_file": out_file,
            "primary_key": self.parameterAsString(parameters, self.PRIMARY_KEY, context),
            "fields": self.parameterAsString(parameters, self.FIELDS, context),
            "ignore_fields": self.parameterAsString(parameters, self.IGNORE_FIELDS, context),
            "hash_key": self.parameterAsString(parameters, self.HASH_KEY, context) or "fcd_hash_id",
            "hash_fields": self.parameterAsString(parameters, self.HASH_FIELDS, context),
            "precision": precision,
            "crs": self.parameterAsString(parameters, self.CRS, context) or None,
            "suffix_a": self.parameterAsString(parameters, self.SUFFIX_A, context) or "original",
            "suffix_b": self.parameterAsString(parameters, self.SUFFIX_B, context) or "new",
            "drop_null_geometry": self.parameterAsBoolean(
                parameters, self.DROP_NULL_GEOMETRY, context
            ),
            "dump_inputs": self.parameterAsBoolean(parameters, self.DUMP_INPUTS, context),
        }

        feedback.pushInfo(f"Running comparison in {mode} mode...")
        feedback.pushInfo(f"Output: {out_file}")

        if feedback.isCanceled():
            return {}

        if mode == "library":
            run_compare_via_library(params)
        else:
            result = run_compare_via_cli(params)
            if result.stdout:
                feedback.pushInfo(result.stdout)
            if result.stderr:
                feedback.pushWarning(result.stderr)
            if result.returncode != 0:
                raise QgsProcessingException(
                    f"changedetector CLI failed (exit {result.returncode}):\n{result.stderr}"
                )

        feedback.pushInfo("Comparison complete.")

        # Load result layers and return them as outputs
        outputs = {}
        layer_map = {
            self.OUTPUT_NEW: "NEW",
            self.OUTPUT_DELETED: "DELETED",
            self.OUTPUT_MODIFIED_BOTH: "MODIFIED_BOTH",
            self.OUTPUT_MODIFIED_ATTR: "MODIFIED_ATTR",
            self.OUTPUT_MODIFIED_GEOM: "MODIFIED_GEOM",
        }
        for output_id, layer_name in layer_map.items():
            uri = f"{out_file}|layername={layer_name}"
            lyr = QgsVectorLayer(uri, f"FCD_{layer_name}", "ogr")
            if lyr.isValid():
                context.temporaryLayerStore().addMapLayer(lyr)
                outputs[output_id] = lyr.id()

        return outputs


class AddHashKeyAlgorithm(QgsProcessingAlgorithm):
    """Add a hash-based primary key column to a spatial dataset.

    Equivalent to: changedetector add-hash-key <in_file> <out_file> [options]
    """

    IN_FILE = "IN_FILE"
    IN_LAYER = "IN_LAYER"
    OUT_FILE = "OUT_FILE"
    OUT_LAYER = "OUT_LAYER"
    HASH_KEY = "HASH_KEY"
    HASH_FIELDS = "HASH_FIELDS"
    PRECISION = "PRECISION"
    CRS = "CRS"
    DROP_NULL_GEOMETRY = "DROP_NULL_GEOMETRY"

    OUTPUT = "OUTPUT"

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return AddHashKeyAlgorithm()

    def name(self):
        return "addhashkey"

    def displayName(self):
        return self.tr("Add Hash Key")

    def group(self):
        return self.tr("Change Detection")

    def groupId(self):
        return "changedetection"

    def shortHelpString(self):
        return self.tr(
            "Add a SHA1 hash-based primary key column to a spatial dataset.\n\n"
            "The hash is computed from geometry (and optionally specified attribute fields), "
            "making each feature uniquely identifiable for subsequent change detection."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.IN_FILE,
                self.tr("Input file"),
                behavior=QgsProcessingParameterFile.File,
                fileFilter="Spatial files (*.shp *.gpkg *.geojson);;All files (*)",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.IN_LAYER,
                self.tr("Layer name within input file"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.OUT_FILE,
                self.tr("Output .gdb path"),
                behavior=QgsProcessingParameterFile.File,
                optional=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.OUT_LAYER,
                self.tr("Output layer name"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.HASH_KEY,
                self.tr("Hash key column name"),
                defaultValue="fcd_hash_id",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.HASH_FIELDS,
                self.tr("Additional fields to include in hash (comma-separated)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.PRECISION,
                self.tr("Coordinate precision"),
                options=PRECISION_LABELS,
                defaultValue=2,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.CRS,
                self.tr("Reproject to CRS (e.g. EPSG:3005; leave blank for original)"),
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DROP_NULL_GEOMETRY,
                self.tr("Drop records with null geometry"),
                defaultValue=False,
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(self.OUTPUT, self.tr("Output layer with hash key"))
        )

    def processAlgorithm(self, parameters, context, feedback):
        from .utils import (
            check_fit_changedetector,
            run_add_hash_key_via_cli,
            run_add_hash_key_via_library,
        )

        mode, _ = check_fit_changedetector()
        if mode == "unavailable":
            raise QgsProcessingException("fit_changedetector is not installed.")

        precision_idx = self.parameterAsEnum(parameters, self.PRECISION, context)

        params = {
            "in_file": self.parameterAsFile(parameters, self.IN_FILE, context),
            "in_layer": self.parameterAsString(parameters, self.IN_LAYER, context) or None,
            "out_file": self.parameterAsFile(parameters, self.OUT_FILE, context),
            "out_layer": self.parameterAsString(parameters, self.OUT_LAYER, context) or None,
            "hash_key": self.parameterAsString(parameters, self.HASH_KEY, context) or "fcd_hash_id",
            "hash_fields": self.parameterAsString(parameters, self.HASH_FIELDS, context),
            "precision": PRECISIONS[precision_idx],
            "crs": self.parameterAsString(parameters, self.CRS, context) or None,
            "drop_null_geometry": self.parameterAsBoolean(
                parameters, self.DROP_NULL_GEOMETRY, context
            ),
        }

        feedback.pushInfo(f"Adding hash key in {mode} mode...")

        if mode == "library":
            run_add_hash_key_via_library(params)
        else:
            result = run_add_hash_key_via_cli(params)
            if result.stdout:
                feedback.pushInfo(result.stdout)
            if result.stderr:
                feedback.pushWarning(result.stderr)
            if result.returncode != 0:
                raise QgsProcessingException(
                    f"changedetector CLI failed (exit {result.returncode}):\n{result.stderr}"
                )

        out_layer_name = params.get("out_layer") or params.get("in_layer") or "output"
        uri = f"{params['out_file']}|layername={out_layer_name}"
        lyr = QgsVectorLayer(uri, f"hash_key_{out_layer_name}", "ogr")
        if lyr.isValid():
            context.temporaryLayerStore().addMapLayer(lyr)
            return {self.OUTPUT: lyr.id()}

        return {}
