"""기상청 ASOS 일자료 수집: 관측소마다 (1) 평년 기간 1991~2020 (2) 분석 기간.

응답 한 건이 약 1.2KB이고 메시지 한도가 1000KB 라서 한 페이지는 500행으로 받는다.
30년치는 관측소당 약 22페이지, 분석 기간은 2페이지 → 전체 약 2,300회(일일 한도 10,000회 안).
관측소별로 기록이 1991년 이후에 시작됐으면 해당 구간 응답이 비어 있을 뿐 오류가 아니다.
"""
from concurrent.futures import ThreadPoolExecutor

from api import QuotaExceeded, fetch_cached
from config import (ASOS_DAILY_LIMIT, BASELINE_FIRST_YEAR, BASELINE_LAST_YEAR, CACHE,
                    END_YMD, LIMIT_MARGIN, START_YMD)
from stations import STATIONS

URL = "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
API = "asos"
PAGE = 500


def fetch_station_range(stn: int, start: str, end: str):
    """한 관측소·한 기간의 모든 페이지를 받아 캐시한다."""
    page = 1
    while True:
        params = dict(numOfRows=PAGE, pageNo=page, dataType="JSON", dataCd="ASOS", dateCd="DAY",
                      startDt=start, endDt=end, stnIds=stn)
        cache = CACHE / "asos" / f"{stn}_{start}_{end}_p{page}.json"
        data = fetch_cached(API, int(ASOS_DAILY_LIMIT * LIMIT_MARGIN), URL, params, cache)
        body = data["response"]["body"] if "body" in data.get("response", {}) else {}
        # 기록이 없는 기간은 body 없이 오류 코드(03 NODATA)만 오는 경우가 있어 그대로 종료한다.
        if not body or page * PAGE >= int(body.get("totalCount", 0)):
            return
        page += 1


def fetch_station(stn: int):
    fetch_station_range(stn, f"{BASELINE_FIRST_YEAR}0101", f"{BASELINE_LAST_YEAR}1231")
    fetch_station_range(stn, START_YMD, END_YMD)
    print("완료", stn, STATIONS[stn], flush=True)


def main():
    try:
        # 초당 최대 30건까지 허용되므로 스레드 16개여도 여유 있다(응답이 느려 스레드가 많아야 처리량이 나온다).
        with ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(fetch_station, STATIONS))
    except QuotaExceeded as e:
        print(e)


if __name__ == "__main__":
    main()
