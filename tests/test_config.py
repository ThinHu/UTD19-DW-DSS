from utd19_dw.config import settings

def test_settings_loaded():
    assert settings.CITIES is not None
    assert isinstance(settings.CITIES, list)
    assert "luzern" in settings.CITIES
    assert settings.START_DATE == "2015-01-01"
    assert settings.END_DATE == "2015-06-30"
    assert settings.FLOW_MAX > 0
    assert settings.INTERVAL_OOR_MODE in ["reject", "rollover"]

def test_dq_mask_calculation():
    mask = settings.get_dq_mask(["RULE_NULL_FLOW", "RULE_FLOW_MAX"])
    assert mask == (1 | 4)
    assert mask == 5

def test_paths_resolved():
    assert settings.RAW_DATA_DIR.is_absolute()
    assert settings.WORK_DIR.is_absolute()
    assert settings.EXPORT_DIR.is_absolute()
    assert settings.DB_PATH.is_absolute()


def test_mart_exclude_rules_exist():
    """Mọi id trong exclude_rules_in_mart phải có trong dq_rules.yaml, nếu không mask sẽ bằng 0."""
    ids = {r["id"] for r in settings.dq_rules}
    assert set(settings.EXCLUDE_RULES_IN_MART) <= ids
    assert settings.get_dq_mask(settings.EXCLUDE_RULES_IN_MART) > 0


def test_sql_dq_bits_match_rules():
    """Bit gán trong 22_clean_measurements.sql phải khớp bit_value của dq_rules.yaml."""
    sql = (settings.BASE_DIR / "sql" / "20_clean" / "22_clean_measurements.sql").read_text(encoding="utf-8")
    for r in settings.dq_rules:
        if r["id"] in ("RULE_INTERVAL_OOR", "RULE_SPEED_OOR"):   # cách ly / không dùng speed, không gắn cờ
            continue
        assert f"THEN {r['bit_value']} ELSE 0 END) " in sql and r["id"] in sql, r["id"]
