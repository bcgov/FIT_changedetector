import geopandas
from changedetector import gdf_diff


def test_diff():
    # one instance of each type of change is found
    # when comparing these two test files
    df_a = geopandas.read_file("test_parks_a.geojson")
    df_b = geopandas.read_file("test_parks_b.geojson")
    d = gdf_diff(df_a, df_b, primary_key="fcd_load_id", return_type="gdf")
    assert len(d["NEW"] == 1)
    assert len(d["DELETED"] == 1)
    assert len(d["MODIFIED_BOTH"] == 1)
    assert len(d["MODIFIED_ATTR"] == 1)
    assert len(d["MODIFIED_GEOM"] == 1)
