"""Transport-neutral application failures."""
class ApplicationError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)

def db_error(exc: Exception) -> ApplicationError:
    return ApplicationError(status_code=503, detail="数据库暂不可用")

def database_error() -> ApplicationError:
    # Do not include host, account, SQL, or password details in API responses.
    return ApplicationError(status_code=503, detail="数据库暂不可用，请检查连接、库权限和建表状态")
