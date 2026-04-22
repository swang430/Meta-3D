#!/usr/bin/env python3
"""
数据库状态检查脚本

用于在项目启动前（如 npm run dev:safe:all）检查数据库状态。
返回值（仅打印第一行标准输出）：
- OK: 数据库连接正常且已初始化数据
- EMPTY: 数据库连接正常，但缺乏核心数据（需运行首次安装向导）
- ERROR: 数据库连接失败
"""
import sys
import os

# 将 api-service 添加到 sys.path 以便于绝对导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.config import settings

def main():
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    try:
        # 1. 尝试建立连接
        with engine.connect() as connection:
            pass
    except OperationalError:
        print("ERROR")
        return

    # 2. 检查数据是否为空
    db = SessionLocal()
    try:
        from app.models.instrument import InstrumentCategory
        from sqlalchemy import func
        count = db.query(func.count(InstrumentCategory.id)).scalar()
        if count == 0:
            print("EMPTY")
        else:
            print("OK")
    except ProgrammingError:
        # 表不存在
        print("EMPTY")
    except Exception as e:
        print("ERROR")
    finally:
        db.close()

if __name__ == "__main__":
    main()
