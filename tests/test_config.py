from utd19_dw.config import settings

def test_settings_loaded():
    assert settings.CITIES is not None
    assert isinstance(settings.CITIES, list)
    assert "luzern" in settings.CITIES
    assert settings.START_DATE == "2019-01-01"
    assert settings.END_DATE == "2019-06-30"
    assert settings.FLOW_MAX > 0
    assert settings.INTERVAL_OOR_MODE in ["quarantine", "null"]

def test_dq_mask_calculation():
    mask = settings.get_dq_mask(["RULE_NULL_FLOW", "RULE_FLOW_MAX"])
    assert mask == (1 | 4)
    assert mask == 5

def test_paths_resolved():
    assert settings.RAW_DATA_DIR.is_absolute()
    assert settings.WORK_DIR.is_absolute()
    assert settings.EXPORT_DIR.is_absolute()
    assert settings.DB_PATH.is_absolute()
