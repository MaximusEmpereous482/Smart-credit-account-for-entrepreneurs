from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Файл базы данных будет создан автоматически в папке orchestrator
SQLALCHEMY_DATABASE_URL = "sqlite:///./orchestrator.db"

# check_same_thread=False нужен только для SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс, от которого наследуются все таблицы
Base = declarative_base()


# Функция для получения сессии БД (будем использовать в роутах)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()