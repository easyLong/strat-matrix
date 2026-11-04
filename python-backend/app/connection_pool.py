"""Bounded, dedicated MySQL leases behind db.connection(); no SQL replay on errors."""
from contextlib import contextmanager
from threading import BoundedSemaphore
import re

import pymysql
from dbutils.pooled_db import PooledDB


class TrackedCursor:
    def __init__(self,cursor,owner):
        self._cursor,self._owner=cursor,owner

    def execute(self,sql,*args,**kwargs):
        text=sql.upper() if isinstance(sql,str) else ''
        if re.search(r'\bGET_LOCK\s*\(',text):
            self._owner.named_lock=True
        if text.lstrip().startswith('SET TRANSACTION'):
            self._owner.isolation_changed=True
        elif text.lstrip().startswith(('SET ','USE ','CREATE TEMPORARY')):
            self._owner.discard=True
        return self._cursor.execute(sql,*args,**kwargs)

    def __getattr__(self,name):return getattr(self._cursor,name)
    def __iter__(self):return iter(self._cursor)
    def __enter__(self):return self
    def __exit__(self,*args):self._cursor.close()


class Lease:
    def __init__(self,connection):
        self._connection=connection
        self.named_lock=False
        self.isolation_changed=False
        self.discard=False

    def cursor(self,*args,**kwargs):return TrackedCursor(self._connection.cursor(*args,**kwargs),self)
    def autocommit(self,value):
        self.discard=True
        return self._connection.autocommit(value)
    def select_db(self,name):
        self.discard=True
        return self._connection.select_db(name)
    def __getattr__(self,name):return getattr(self._connection,name)


class MySQLPool:
    def __init__(self,settings,*,size=16,timeout=5,pool=None):
        self._slots=BoundedSemaphore(size)
        self._timeout=timeout
        self._closed=False
        self._pool=pool or PooledDB(pymysql,mincached=0,maxcached=size,maxshared=0,
            maxconnections=size,blocking=False,reset=False,ping=1,
            # Reconnecting and replaying a statement could lose row/named locks.
            # Only checkout ping may reconnect; statement failures propagate.
            isfatal=lambda error:False,**settings)

    @contextmanager
    def connection(self):
        if not self._slots.acquire(timeout=self._timeout):
            raise pymysql.OperationalError(1205,'数据库连接池繁忙，请稍后重试')
        raw=None
        try:
            if self._closed:raise pymysql.OperationalError(2006,'数据库连接池已关闭')
            raw=self._pool.connection(shareable=False)
            lease=Lease(raw)
            try:
                yield lease
            finally:
                try:
                    raw.rollback()
                    if lease.named_lock:
                        with raw.cursor() as cursor:cursor.execute('SELECT RELEASE_ALL_LOCKS()')
                    if lease.isolation_changed:
                        if lease.named_lock:raw.rollback()
                        with raw.cursor() as cursor:
                            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                except Exception:
                    # Pinned DBUtils proxy: close its physical SteadyDB handle
                    # before returning the lease, so a dirty connection is never
                    # offered to a different caller. Next checkout reconnects.
                    raw._con.close()
                if self._closed or lease.discard:raw._con.close()
        finally:
            try:
                if raw is not None:raw.close()
            finally:self._slots.release()

    def close(self):
        self._closed=True
        self._pool.close()
