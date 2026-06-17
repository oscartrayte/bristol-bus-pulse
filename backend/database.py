"""Database initialization and session management."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import logging

from config import settings
from models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self):
        self.engine: AsyncEngine = None
        self.session_factory: async_sessionmaker = None
    
    async def initialize(self) -> None:
        """Initialize database engine and session factory."""
        logger.info(f"Initializing database: {settings.database_url}")
        
        self.engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            poolclass=NullPool,  # Disable connection pooling for asyncpg
            connect_args={
                "timeout": 30,
                "command_timeout": 30,
                "server_settings": {
                    "jit": "off",
                    "application_name": "bristol_bus_pulse",
                }
            }
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown database engine."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database engine disposed")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self.session_factory() as session:
            try:
                yield session
            finally:
                await session.close()
    
    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.session_factory() as session:
                await session.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with db_manager.get_session() as session:
        yield session
