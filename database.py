from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

#SQLALCHEMY_DATABASE_URL = "mysql+aiomysql://root:Cqc114514!@192.168.1.101/Car_data"
SQLALCHEMY_DATABASE_URL = "mysql+aiomysql://root:xhtxht0715@localhost/data"

# 2. 创建异步引擎
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,        # 建议开发环境开启，可以看到生成的 SQL 语句
    future=True       # 确保使用 SQLAlchemy 2.0 风格
)

# 3. 创建异步会话工厂
# 使用 async_sessionmaker 并指定 class_ 为 AsyncSession
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=AsyncSession,
    expire_on_commit=False  # 异步环境下建议设为 False，防止访问属性时触发意外的 I/O
)

class Base(DeclarativeBase):
    pass

# 4. 修改为异步依赖注入函数
async def get_db():
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            # 使用 async with 实际上已经自动处理了关闭
            # 这里的 await db.close() 是可选的，但显式写出结构更清晰
            await db.close()