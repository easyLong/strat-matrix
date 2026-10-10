"""Small JSON HTTP client shared by internal vector workers."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WorkerError(Exception):
    pass


class StaleResult(WorkerError):
    pass


def json_request(url: str, method: str, *, body: dict | None = None,
                 headers: dict[str, str] | None = None, timeout: int = 30,
                 stale_conflict: bool = False) -> dict:
    try:
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8") if body is not None else None
        request = Request(url, data=data, method=method, headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
            **(headers or {}),
        })
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        if stale_conflict and exc.code in (404, 409):
            raise StaleResult(f"HTTP {exc.code}") from exc
        # Do not copy URLs, tokens, response bodies or raw model inputs into
        # the database failure reason or process log.
        raise WorkerError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise WorkerError(f"请求失败：{type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise WorkerError("响应必须是 JSON 对象")
    return result
