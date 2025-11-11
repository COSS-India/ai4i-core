import os
from sqlalchemy import create_engine, inspect , text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from logger import logger

load_dotenv()



DB_USER     = str(os.getenv("APP_DB_USER", "dhruva_user"))
DB_PASSWORD = str(os.getenv("APP_DB_PASSWORD", "dhruva_secure_password_2024"))
DB_HOST     = str(os.getenv("APP_DB_HOST", "localhost"))
DB_PORT     = int(os.getenv("APP_DB_PORT",5434))
DB_NAME     = str(os.getenv("APP_DB_NAME", "dhruva_platform"))
DB_SCHEMA   = os.getenv("APP_DB_SCHEMA", "model_management_db")



# PostgreSQL connection engines
app_db_engine = None

# Session makers
AppDBSessionLocal = None

# Base classes for SQLAlchemy models
AppDBBase = declarative_base()

def init_postgresql_connections():
    """Initialize PostgreSQL database connections"""
    global app_db_engine, AppDBSessionLocal
    
    try:
        # App database connection
        app_db_connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

        app_db_engine = create_engine(
            app_db_connection_string,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False  # Set to True for SQL debugging
        )

        AppDBSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=app_db_engine
        )

        logger.info(f"Connected to PostgreSQL: {DB_NAME}@{DB_HOST}:{DB_PORT}")
    except Exception as e:
        logger.exception(f"Error connecting to PostgreSQL: {e}")
        raise
    

def get_app_db_session():
    """Get a database session for the app database"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    
    db = AppDBSessionLocal()
    try:
        yield db
    finally:
        db.close()


# def check_or_create_schema():
#     """Create the database schema if it doesn't already exist."""
#     if app_db_engine is None:
#         init_postgresql_connections()

#     try:
#         with app_db_engine.connect() as conn:
#             conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
#             conn.commit()
#         logger.info(f"Verified schema: '{DB_SCHEMA}' exists or created.")
#     except Exception as e:
#         logger.exception(f"Error while verifying/creating schema '{DB_SCHEMA}': {e}")
#         raise


def create_tables():
    """Check existing tables and create missing ones"""
    if app_db_engine is None:
        init_postgresql_connections()

    # check_or_create_schema()

    inspector = inspect(app_db_engine)
    # existing_tables = inspector.get_table_names(schema=DB_SCHEMA)
    existing_tables = inspector.get_table_names()
    all_tables = AppDBBase.metadata.tables.keys()

    missing_tables = [t for t in all_tables if t not in existing_tables]
    if missing_tables:
        logger.info(f"Creating missing tables: {missing_tables}")
        AppDBBase.metadata.create_all(bind=app_db_engine)
    else:
        logger.info("All database tables already exist.")

# Legacy compatibility function for existing code
def AppDatabase() -> Session:
    """Legacy compatibility function - returns app database session"""
    if AppDBSessionLocal is None:
        init_postgresql_connections()
    return AppDBSessionLocal()

# Initialize connections on module import
init_postgresql_connections()
