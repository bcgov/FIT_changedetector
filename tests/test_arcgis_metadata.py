"""Tests for arcgis/changedetector_metadata.py: parsing the tool metadata
text from the arcgis README, and applying it to a tool's metadata XML. arcpy
is only needed to read/save a real toolbox, so it is stubbed for apply()."""

import importlib.util
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ARCGIS_DIR = ROOT / "src" / "fit_changedetector" / "arcgis"
metadata = _load("changedetector_metadata", ARCGIS_DIR / "changedetector_metadata.py")

MARKDOWN = """# Title

## Tool metadata

Intro text.

### `a.py` (tool: tool_a)

**Summary:** Summary A.

**Description:** Description A.

**Usage:** Usage A.

**Syntax:**
- **First Param** - Text for **first**.
- **Suffix - Original** - Label containing a dash.
- **Output File** *(Derived)* - Derived output.

### `b.py` (tool: tool_b)

**Summary:** Summary B.

**Description:** Description B.

**Usage:** Usage B.

**Syntax:** same as tool_a, plus Extra:
- **First Param**, **Suffix - Original** - as in tool_a above.
- **Extra** - Only in b.

## Next section

- **Ignored** - not part of tool metadata.
"""


def test_parse_tools_fields_and_parameters():
    tools = metadata.parse(MARKDOWN)
    assert list(tools) == ["tool_a", "tool_b"]
    assert tools["tool_a"]["summary"] == "Summary A."
    assert tools["tool_a"]["usage"] == "Usage A."
    assert tools["tool_a"]["parameters"] == {
        "First Param": "Text for **first**.",
        "Suffix - Original": "Label containing a dash.",
        "Output File": "Derived output.",
    }


def test_parse_resolves_as_in_other_tool():
    params = metadata.parse(MARKDOWN)["tool_b"]["parameters"]
    assert params == {
        "First Param": "Text for **first**.",
        "Suffix - Original": "Label containing a dash.",
        "Extra": "Only in b.",
    }


def test_parse_unresolvable_reference_raises():
    markdown = MARKDOWN.replace(
        "- **Extra** - Only in b.", "- **Extra** - as in tool_a above."
    )
    with pytest.raises(ValueError, match="'Extra' refers to tool_a"):
        metadata.parse(markdown)


def test_parse_missing_field_raises():
    with pytest.raises(ValueError, match="tool_a: missing \\['usage'\\]"):
        metadata.parse(MARKDOWN.replace("**Usage:** Usage A.", ""))


def test_parse_readme_matches_parameter_tables():
    """Every parameter of both tools has text - 16 for diff2json, 17 for
    diff2gdb, as in the README's Parameters tables."""
    tools = metadata.parse(metadata.README.read_text(encoding="utf-8"))
    assert len(tools["diff2json"]["parameters"]) == 16
    assert len(tools["diff2gdb"]["parameters"]) == 17
    for tool in tools.values():
        for text in tool["parameters"].values():
            assert not metadata.SAME_AS.match(text)


def _tool_xml(*labels):
    params = "".join(
        f'<param name="p{i}" displayname="{label}"/>' for i, label in enumerate(labels)
    )
    return f'<metadata><tool name="tool_a"><parameters>{params}</parameters></tool></metadata>'


TOOL_A = metadata.parse(MARKDOWN)["tool_a"]


def test_update_metadata_xml_sets_parameter_explanations():
    xml, unmatched, unused = metadata.update_metadata_xml(
        _tool_xml("First Param", "Suffix - Original", "Output File"), TOOL_A
    )
    assert unmatched == []
    assert unused == []
    param = ET.fromstring(xml).find("tool/parameters/param")
    dialog = param.find("dialogReference").text
    assert param.find("pythonReference").text == dialog
    assert '<SPAN STYLE="font-weight:bold;">first</SPAN>' in dialog
    assert "**" not in dialog


def test_update_metadata_xml_sets_tool_text():
    root = ET.fromstring(
        metadata.update_metadata_xml(_tool_xml("First Param"), TOOL_A)[0]
    )
    assert "Summary A." in root.find("tool/summary").text
    assert "Usage A." in root.find("tool/usage").text
    assert root.find("dataIdInfo/idPurp").text == "Summary A."
    assert "Description A." in root.find("dataIdInfo/idAbs").text


def test_update_metadata_xml_reports_unmatched_and_unused():
    _, unmatched, unused = metadata.update_metadata_xml(
        _tool_xml("First Param", "Renamed Param"), TOOL_A
    )
    assert unmatched == ["Renamed Param"]
    assert unused == ["Suffix - Original", "Output File"]


def test_update_metadata_xml_replaces_existing_text():
    xml = _tool_xml("First Param").replace(
        'displayname="First Param"/>',
        'displayname="First Param"><dialogReference>old</dialogReference></param>',
    )
    param = ET.fromstring(metadata.update_metadata_xml(xml, TOOL_A)[0]).find(
        "tool/parameters/param"
    )
    assert len(param.findall("dialogReference")) == 1
    assert "Text for" in param.find("dialogReference").text


def test_update_metadata_xml_without_parameters_raises():
    with pytest.raises(ValueError, match="no tool parameters found"):
        metadata.update_metadata_xml("<metadata/>", TOOL_A)


def test_to_html_escapes_and_drops_backticks():
    assert metadata.to_html("a < b, `0.01`") == (
        '<DIV STYLE="text-align:Left;"><P><SPAN>a &lt; b, 0.01</SPAN></P></DIV>'
    )


@pytest.fixture
def fake_arcpy(monkeypatch, tmp_path):
    """arcpy stub whose Metadata objects hold a tool's XML, plus a one-tool
    README for apply() to read."""
    arcpy = MagicMock()
    docs = {}

    def make(path):
        md = docs.setdefault(path, MagicMock(xml=_tool_xml("First Param")))
        return md

    arcpy.metadata.Metadata.side_effect = make
    monkeypatch.setitem(sys.modules, "arcpy", arcpy)
    readme = tmp_path / "README.md"
    # tool_a only - tool_b's tool isn't in the stub toolbox
    readme.write_text(MARKDOWN[: MARKDOWN.index("### `b.py`")] + "## End\n")
    monkeypatch.setattr(metadata, "README", readme)
    return docs


def test_apply_saves_and_reports(fake_arcpy, capsys):
    ok = metadata.apply("toolbox.atbx")
    md = next(iter(fake_arcpy.values()))
    md.save.assert_called_once()
    assert "Text for" in md.xml
    # two of TOOL_A's texts have no matching parameter
    assert not ok
    assert "no parameter labelled 'Output File'" in capsys.readouterr().out


def test_apply_dry_run_does_not_save(fake_arcpy, capsys):
    metadata.apply("toolbox.atbx", dry_run=True)
    md = next(iter(fake_arcpy.values()))
    md.save.assert_not_called()
    assert "Dry run" in capsys.readouterr().out


def test_candidate_names():
    assert metadata.candidate_names("diff2gdb") == [
        "diff2gdb",
        "changedetectordiff2gdb",
    ]
    assert metadata.candidate_names("diff2gdb", {"diff2gdb": "MyTool"}) == ["MyTool"]
    # a key with no Name given still falls back to the defaults
    assert metadata.candidate_names("diff2gdb", {"diff2gdb": None}) == [
        "diff2gdb",
        "changedetectordiff2gdb",
    ]


def test_apply_falls_back_to_prefixed_name(fake_arcpy, capsys):
    """A tool named changedetector<key> is found when <key> isn't - arcpy
    returns blank metadata (no parameters) for a tool that doesn't exist."""
    missing = os.path.join("toolbox.atbx", "tool_a")
    fake_arcpy[missing] = MagicMock(xml="<metadata/>")
    metadata.apply("toolbox.atbx")
    found = fake_arcpy[os.path.join("toolbox.atbx", "changedetectortool_a")]
    found.save.assert_called_once()
    fake_arcpy[missing].save.assert_not_called()
    assert "tool_a (tool 'changedetectortool_a')" in capsys.readouterr().out


def test_apply_reports_names_tried(fake_arcpy, capsys):
    for name in ("tool_a", "changedetectortool_a"):
        fake_arcpy[os.path.join("toolbox.atbx", name)] = MagicMock(xml="<metadata/>")
    assert not metadata.apply("toolbox.atbx")
    out = capsys.readouterr().out
    assert "tool_a: FAILED" in out
    assert "'tool_a'" in out
    assert "'changedetectortool_a'" in out
    assert "--tool_a <Name>" in out


def test_apply_uses_given_name(fake_arcpy):
    metadata.apply("toolbox.atbx", tool_names={"tool_a": "Custom"})
    assert list(fake_arcpy) == [os.path.join("toolbox.atbx", "Custom")]
