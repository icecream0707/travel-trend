"""data.go.kr 공통 호출 도구: 키 로딩, 재시도, 응답 캐시, 일일 호출 수 집계."""
import json
import os
import threading
import time
from datetime import date
from pathlib import Path

import requests

from config import CACHE, ROOT

_lock = threading.Lock()  # 스레드 여러 개가 호출 수 파일을 동시에 갱신하지 않도록


def service_key() -> str:
    """환경변수 또는 레포 루트 .env 에서 인증키(Decoding 키)를 읽는다."""
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf8").splitlines():
            if line.startswith("DATA_GO_KR_SERVICE_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY 가 .env 에 없습니다.")
    return key


class QuotaExceeded(Exception):
    """오늘 쓸 수 있는 호출 수를 다 썼다. 다음 날 같은 명령을 다시 실행하면 이어받는다."""


def _counter_path(api_name: str) -> Path:
    return CACHE / f"calls_{api_name}_{date.today():%Y%m%d}.txt"


def calls_today(api_name: str) -> int:
    p = _counter_path(api_name)
    return int(p.read_text()) if p.exists() else 0


def fetch_cached(api_name: str, limit: int, url: str, params: dict, cache_file: Path) -> dict:
    """캐시 파일이 있으면 그대로 읽고, 없으면 호출해서 저장한다.

    캐시가 있으면 호출 수에 포함하지 않으므로 중단 후 다시 실행해도 안전하다.
    """
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf8"))

    with _lock:  # 한도 확인과 호출 수 증가를 한 번에 해서 스레드 간 초과를 막는다
        if calls_today(api_name) >= limit:
            raise QuotaExceeded(f"{api_name}: 오늘 호출 한도({limit})에 도달. 내일 다시 실행하세요.")
        CACHE.mkdir(parents=True, exist_ok=True)
        _counter_path(api_name).write_text(str(calls_today(api_name) + 1))

    last_err = None
    for attempt in range(4):                      # 일시적 오류는 점점 길게 쉬며 재시도
        try:
            r = requests.get(url, params={**params, "serviceKey": service_key()}, timeout=60)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"호출 실패: {url} ({type(last_err).__name__})")  # 키가 URL에 있어 메시지에 URL을 안 넣음

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
    return data


def items_of(body: dict) -> list:
    """응답 items.item 을 항상 리스트로 돌려준다(1건이면 dict, 0건이면 빈 문자열로 오는 API 특성)."""
    items = body.get("items")
    if not items:
        return []
    item = items["item"]
    return item if isinstance(item, list) else [item]
