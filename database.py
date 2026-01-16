from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker, DeclarativeBase

SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:Cqc114514!@192.168.31.64/Car_data"
#SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:xhtxht0715@localhost/robot_car_system"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# 这是一个公共函数，谁都要用，所以放在这里
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()