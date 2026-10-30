from database import test_database_connection

try:
    result = test_database_connection()

    print("Database connection successful!")
    print("Database:", result[0])
    print("User:", result[1])

except Exception as error:
    print("Database connection failed.")
    print(type(error).__name__, str(error))