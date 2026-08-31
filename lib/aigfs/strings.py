"""
Canonical strings used throughout uw-aigfs.
"""

from dataclasses import dataclass

# Private

_ = ""  # default value, to be replaced by key


class _ValsMatchKeys:
    def __post_init__(self) -> None:
        attr = "__dataclass_fields__"
        fields = getattr(self, attr).values()
        for field in fields:
            if not getattr(self, field.name):
                object.__setattr__(self, field.name, field.name)


@dataclass(frozen=True)
class _STR(_ValsMatchKeys):
    """
    General strings.
    """

    aige: str = _
    aigefs: str = _
    aigfs: str = _
    aigfs_done: str = "aigfs.done"
    aigfs_ics: str = _
    aigfs_inference: str = _
    aigfs_post: str = _
    aigfs_yaml: str = "aigfs.yaml"
    APCP_surface: str = _
    app: str = _
    attrs: str = _
    base_yaml: str = "base.yaml"
    batch: str = _
    data: str = _
    datetime: str = _
    deliver_to: str = _
    diffs_stddev_path: str = _
    discipline: str = _
    drtn: str = _
    etc: str = _
    files_to_copy: str = _
    files_to_hardlink: str = _
    files_to_link: str = _
    forecast_freq: str = _
    forecast_length: str = _
    geopotential: str = _
    geopotential_at_surface: str = _
    HGT: str = _
    HGT_surface: str = _
    home: str = _
    idx: str = _
    ics: str = _
    ics_path: str = _
    inputfiles: str = _
    json_path: str = _
    LAND_surface: str = _
    land_sea_mask: str = _
    lat: str = _
    latitude: str = _
    level: str = _
    levels: str = _
    load_once: str = _
    lon: str = _
    longitude: str = _
    long_name: str = _
    mean_path: str = _
    mean_sea_level_pressure: str = _
    model_weights_path: str = _
    name: str = _
    outputdir: str = _
    parameter_category: str = "parameterCategory"
    parameter_number: str = "parameterNumber"
    pdtn: str = _
    platform: str = _
    plevel: str = _
    pressure: str = _
    PRMSL_meansealevel: str = _
    rocoto: str = _
    rocoto_xml: str = "rocoto.xml"
    rundir: str = _
    SPFH: str = _
    specific_humidity: str = _
    stddev_path: str = _
    tables_aigefs_json: str = "tables_aigefs.json"
    tables_aigfs_json: str = "tables_aigfs.json"
    templates: str = _
    temperature: str = _
    ten_m_u_component_of_wind: str = "10m_u_component_of_wind"
    ten_m_v_component_of_wind: str = "10m_v_component_of_wind"
    time: str = _
    TMP: str = _
    TMP_2maboveground: str = _
    total_precipitation_6hr: str = _
    total_precipitation_cumsum: str = _
    two_m_temperature: str = "2m_temperature"
    UGRD: str = _
    UGRD_10maboveground: str = _
    u_component_of_wind: str = _
    variable_extraction_yaml: str = _
    vertical_velocity: str = _
    VGRD: str = _
    VGRD_10maboveground: str = _
    v_component_of_wind: str = _
    VVEL: str = _
    weights: str = _
    workflow: str = _


STR = _STR()
