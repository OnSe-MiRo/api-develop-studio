"""Exceptions used by Studio database error handlers."""
import sqlite3

try:
    from psycopg import Error as PostgresError
    from psycopg_pool import PoolTimeout
    DATABASE_ERRORS = (sqlite3.Error, PostgresError, PoolTimeout)
except ImportError:
    DATABASE_ERRORS = (sqlite3.Error,)
