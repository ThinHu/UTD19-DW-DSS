import duckdb
from utd19_dw.db import DBManager

def test_db_manager_in_memory(tmp_path):
    test_db_path = tmp_path / "test.duckdb"
    manager = DBManager(db_path=test_db_path)
    
    # Test execute
    manager.execute("CREATE SCHEMA test_s;")
    manager.execute("CREATE TABLE test_s.t (id INT, val VARCHAR);")
    manager.execute("INSERT INTO test_s.t VALUES (1, 'a'), (2, 'b');")
    
    assert manager.count("test_s.t") == 2
    
    # Test query df
    df = manager.query("SELECT * FROM test_s.t ORDER BY id")
    assert len(df) == 2
    assert df.iloc[0]["val"] == "a"

def test_step_context_manager(tmp_path):
    test_db_path = tmp_path / "test_step.duckdb"
    manager = DBManager(db_path=test_db_path)
    
    manager.execute("CREATE SCHEMA etl;")
    manager.execute("""
    CREATE TABLE etl.run_log (
        step VARCHAR,
        seconds DOUBLE,
        rows_out BIGINT,
        note VARCHAR,
        logged_at TIMESTAMP
    );
    """)
    manager.execute("CREATE TABLE test_tbl (id INT);")
    manager.execute("INSERT INTO test_tbl VALUES (10), (20);")
    
    with manager.step("test_step_name", table="test_tbl", note="Unit test note"):
        pass
        
    logs = manager.query("SELECT * FROM etl.run_log")
    assert len(logs) == 1
    assert logs.iloc[0]["step"] == "test_step_name"
    assert logs.iloc[0]["rows_out"] == 2
