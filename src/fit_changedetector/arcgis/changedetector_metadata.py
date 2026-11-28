"""Apply the script tools' metadata - Summary, Description, Usage, and each
parameter's Dialog and Scripting Explanation - to the tools in a toolbox,
rather than pasting it in by hand via Edit Metadata.

The text is read from the "Tool metadata" section of README.md alongside
this file (installed with the package, so it always matches the installed
tools). Tools are expected to be named diff2gdb and diff2json, and parameters
are matched to the text by their labels - any parameter or text left
unmatched is reported.

Run with ArcGIS Pro's Python (arcpy), with the toolbox closed in Pro:

    "%PROGRAMFILES%\\ArcGIS\\Pro\\bin\\Python\\Scripts\\propy.bat" ^
        <this file> <path to toolbox .atbx> [--dry-run]

Everything except apply() is pure stdlib - arcpy is imported only when
applying the result to a toolbox, so the rest can be tested outside ArcGIS
Pro.
"""

import argparse
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

README = Path(os.path.abspath(__file__)).parent / "README.md"

SECTION = "## Tool metadata"
TOOL_HEADING = re.compile(r"^### .*\(tool: (\w+)\)\s*$")
FIELD = re.compile(r"^\*\*(Summary|Description|Usage):\*\* (.+)$")
# a Syntax bullet: one or more bold labels (comma separated, optionally
# followed by a marker such as *(Derived)*), then " - " and the text. Labels
# can themselves contain " - " (eg "Suffix - Original"), hence matching the
# bold markers rather than splitting on the first " - "
BULLET = re.compile(
    r"^- (?P<labels>\*\*.+?\*\*(?:, \*\*.+?\*\*)*)(?: \*\([^)]*\)\*)? - (?P<text>.+)$"
)
SAME_AS = re.compile(r"^as in (\w+) above\.?$")


def parse(markdown):
    """{tool name: {"summary", "description", "usage", "parameters":
    {label: text}}} from the README's Tool metadata section, with "as in
    <tool> above" parameter text resolved to that tool's text."""
    start = markdown.find(f"\n{SECTION}\n")
    if start == -1:
        raise ValueError(f"README has no '{SECTION}' section")
    section = markdown[start + len(SECTION) + 2 :]
    end = re.search(r"^## ", section, re.MULTILINE)
    if end:
        section = section[: end.start()]

    tools = {}
    tool = None
    for line in section.splitlines():
        heading = TOOL_HEADING.match(line)
        if heading:
            tool = {"summary": "", "description": "", "usage": "", "parameters": {}}
            tools[heading.group(1)] = tool
            continue
        if tool is None:
            continue
        field = FIELD.match(line)
        if field:
            tool[field.group(1).lower()] = field.group(2).strip()
            continue
        bullet = BULLET.match(line)
        if bullet:
            text = bullet.group("text").strip()
            for label in re.findall(r"\*\*(.+?)\*\*", bullet.group("labels")):
                tool["parameters"][label] = text

    for name, tool in tools.items():
        for label, text in tool["parameters"].items():
            same_as = SAME_AS.match(text)
            if not same_as:
                continue
            other = tools.get(same_as.group(1), {}).get("parameters", {})
            if label not in other or SAME_AS.match(other[label]):
                raise ValueError(
                    f"{name}: '{label}' refers to {same_as.group(1)}, which has no "
                    "text of its own for it"
                )
            tool["parameters"][label] = other[label]

    if not tools:
        raise ValueError(f"No '(tool: <name>)' headings found under '{SECTION}'")
    for name, tool in tools.items():
        missing = [f for f in ("summary", "description", "usage") if not tool[f]]
        if missing or not tool["parameters"]:
            raise ValueError(f"{name}: missing {missing or 'Syntax parameters'}")
    return tools


def to_html(text):
    """The README's markdown-ish text as the simple HTML Pro stores metadata
    text as - **bold** kept as bold, `code` backticks dropped."""
    text = html.escape(text, quote=False).replace("`", "")
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r'</SPAN><SPAN STYLE="font-weight:bold;">\1</SPAN><SPAN>',
        text,
    )
    return f'<DIV STYLE="text-align:Left;"><P><SPAN>{text}</SPAN></P></DIV>'


def _set_text(parent, tag, text):
    element = parent.find(tag)
    if element is None:
        element = ET.SubElement(parent, tag)
    element.text = text


def update_metadata_xml(xml_text, tool_metadata):
    """Return (new_xml, unmatched_parameters, unused_labels) - xml_text (a
    tool's metadata XML) with tool_metadata's text applied.

    unmatched_parameters are the tool's parameters (by label, or name if it
    has no label) with no text in tool_metadata; unused_labels are the labels
    in tool_metadata that matched none of the tool's parameters.
    """
    root = ET.fromstring(xml_text)
    tool = root.find("tool")
    parameters = tool.find("parameters") if tool is not None else None
    if parameters is None:
        raise ValueError(
            "no tool parameters found in the metadata - open the tool's Edit "
            "Metadata view once and Save, then re-run"
        )

    _set_text(tool, "summary", to_html(tool_metadata["summary"]))
    _set_text(tool, "usage", to_html(tool_metadata["usage"]))
    data_id_info = root.find("dataIdInfo")
    if data_id_info is None:
        data_id_info = ET.SubElement(root, "dataIdInfo")
    _set_text(data_id_info, "idPurp", tool_metadata["summary"].replace("`", ""))
    _set_text(data_id_info, "idAbs", to_html(tool_metadata["description"]))

    texts = tool_metadata["parameters"]
    used = set()
    unmatched = []
    for param in parameters.findall("param"):
        label = param.get("displayname") or param.get("name")
        if label not in texts:
            unmatched.append(label)
            continue
        used.add(label)
        explanation = to_html(texts[label])
        _set_text(param, "dialogReference", explanation)
        _set_text(param, "pythonReference", explanation)

    unused = [label for label in texts if label not in used]
    return ET.tostring(root, encoding="unicode"), unmatched, unused


def apply(toolbox, dry_run=False):
    """Apply the metadata to each tool in toolbox. Returns True if every tool
    was found and every parameter matched."""
    import arcpy  # only available in ArcGIS Pro's Python

    tools = parse(README.read_text(encoding="utf-8"))
    ok = True
    for name, tool_metadata in tools.items():
        path = os.path.join(toolbox, name)
        try:
            md = arcpy.metadata.Metadata(path)
            new_xml, unmatched, unused = update_metadata_xml(md.xml, tool_metadata)
        # report each tool's failure and carry on with the rest - arcpy's own
        # exception types vary (ExecuteError, RuntimeError, OSError, ...)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: FAILED - {e}")
            ok = False
            continue
        matched = len(tool_metadata["parameters"]) - len(unused)
        print(f"{name}: {matched} parameter(s) matched")
        for label in unmatched:
            print(f"  no text for parameter '{label}' (left unchanged)")
        for label in unused:
            print(f"  no parameter labelled '{label}' (text not applied)")
        ok = ok and not unmatched and not unused
        if not dry_run:
            md.xml = new_xml
            md.save()
    if dry_run:
        print("Dry run - nothing saved")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("toolbox", help="Path to the toolbox (.atbx) holding the tools")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be matched, without saving",
    )
    args = parser.parse_args(argv)
    return 0 if apply(args.toolbox, args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())
