import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

DATABASE_URL = os.getenv(
    "MEMORYPAL_ARCHIVE_DATABASE_URL",
    "postgresql://postgres@localhost:5432/memoripal"
)

engine = create_engine(
    DATABASE_URL,
    echo=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
