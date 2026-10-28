from utd19_dw.pipeline import render_sql
from utd19_dw.config import settings

def test_render_sql_basic():
    template = "SELECT '{CITY_IN}' AS cities, {FLOW_MAX} AS max_flow {DATE_FILTER_SQL};"
    rendered = render_sql(template)
    assert str(settings.FLOW_MAX) in rendered
    assert "luzern" in rendered
    assert "2019-01-01" in rendered
    assert "2019-06-30" in rendered

def test_render_sql_brackets_safety():
    sql_template = """
    SELECT '{CITY_IN}' AS cities, {FLOW_MAX} AS max_f
    FROM test
    WHERE col ~ '^[0-9]{1,3}$'
    """
    rendered = render_sql(sql_template)
    assert "^[0-9]{1,3}$" in rendered
    assert str(settings.FLOW_MAX) in rendered
