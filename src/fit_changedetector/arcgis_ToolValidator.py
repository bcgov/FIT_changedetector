# ruff: noqa: F401
# ruff: noqa: E402
# ruff: noqa: F821

# paste this into the Validation tab of the script tool properties

IGNORE_FIELDS = [
    "OBJECTID",
    "OID_",  # ArcPro adds this to csv files
    "FID",
    "GLOBALID",
    "GLOBAL_ID",
    "SHAPE_LENGTH",
    "SHAPE_LENG",  # .shp truncation
    "SHAPE",
    "SHAPE_AREA",
    "GEOMETRY_LENGTH",
    "GEOMETRY_AREA",
    "GEOMETRY",
    "SHAPE",
]


class ToolValidator:
    # Class to add custom behavior and properties to the tool and tool parameters.

    def __init__(self):
        # Set self.params for use in other validation methods.
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self):
        # Customize parameter properties. This method gets called when the
        # tool is opened.
        return

    def updateParameters(self):
        # Modify the values and properties of parameters before internal
        # validation is performed.

        # Toggle the Include or Exclude field visibility to make them mutually exclusive.
        if self.params[4].value is not None:  # Include
            self.params[5].value = None
            self.params[5].enabled = 0
        elif self.params[5].value is not None:  # Exclude
            self.params[4].value = None
            self.params[4].enabled = 0
        else:
            self.params[4].enabled = 1
            self.params[5].enabled = 1

        # set default coordinate precision based on spatial reference
        sr = arcpy.Describe(self.params[0].value).spatialReference
        if sr.type.lower() == "geographic" and sr.angularUnitName.lower() == "degree":
            self.params[8].value = 0.00001
        elif sr.type.lower() == "projected" and sr.linearUnitName.lower() == "meter":
            self.params[8].value = 1
        else:
            arcpy.AddError("Incompatible spatial reference units, must be degree or meter")

        # populate possible field names to pk/include/exclude/hash field parameters,
        # including fields common to both sources and not in the ignore list
        if self.params[0].value is not None and self.params[1].value is not None:
            fields_1 = [f.name for f in arcpy.ListFields(self.params[0].value)]
            fields_2 = [f.name for f in arcpy.ListFields(self.params[1].value)]

            # intersect to get the common fields
            common_fields = list(set(fields_2).intersection(set(fields_1)))
            common_fields = [f for f in common_fields if f.upper() not in IGNORE_FIELDS]

            # ordering is lost after converting into sets, re-order based on first input fc
            fieldlist = [f for f in fields_1 if f in common_fields]

            self.params[3].filter.list = fieldlist
            self.params[4].filter.list = fieldlist
            self.params[5].filter.list = fieldlist
            self.params[7].filter.list = fieldlist

    def updateMessages(self):
        # Modify the messages created by internal validation for each tool
        # parameter. This method is called after internal validation.
        return

    # def isLicensed(self):
    #     # Set whether the tool is licensed to execute.
    #     return True

    # def postExecute(self):
    #     # This method takes place after outputs are processed and
    #     # added to the display.
    #     return
