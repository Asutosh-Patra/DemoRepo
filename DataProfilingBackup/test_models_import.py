from database import Base
import models

expected_tables = {
    "users",
    "projects",
    "connections",
    "profiling_configs",
    "profiling_runs",
    "profiling_results",
}

actual_tables = set(Base.metadata.tables.keys())

print("Expected tables:", sorted(expected_tables))
print("Loaded tables:", sorted(actual_tables))

if actual_tables == expected_tables:
    print("SUCCESS: All six SQLAlchemy models loaded.")
else:
    print("ERROR: Model table names do not match.")