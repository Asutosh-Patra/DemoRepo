from schemas import ProjectCreate, ConnectionCreate

project = ProjectCreate(
    organization_name="ABC Retail",
    name="Customer Data Quality",
)

print("Project schema valid:", project.name)

connection = ConnectionCreate(
    project_id="11111111-1111-1111-1111-111111111111",
    name="Customer CSV",
    connection_role="source",
    source_type="csv",
)

print("Connection schema valid:", connection.name)