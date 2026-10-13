"""데이터랩 '기초 지자체 지역방문자수' 일 단위 데이터를 월 단위 구간으로 나눠 수집한다.

한 요청 최대 1000행. 하루 약 800행(시군구 약 270 × 현지인/외지인/외국인)이므로
한 달(약 25,000행)은 약 25페이지다. 24개월이면 약 600회로 일일 한도(1,000회) 안이다.
"""
import calendar

from api import QuotaExceeded, fetch_cached
from config import CACHE, END_YMD, LIMIT_MARGIN, START_YMD, VISITOR_DAILY_LIMIT

URL = "https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList"
API = "visitors"
PAGE = 1000


def month_ranges():
    """START~END 를 달 단위 (시작, 끝) 문자열 목록으로 쪼갠다."""
    y, m = int(START_YMD[:4]), int(START_YMD[4:6])
    ey, em = int(END_YMD[:4]), int(END_YMD[4:6])
    while (y, m) <= (ey, em):
        last = calendar.monthrange(y, m)[1]
        yield f"{y}{m:02d}01", f"{y}{m:02d}{last:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_range(start: str, end: str):
    """한 구간의 모든 페이지를 받아 캐시한다."""
    page = 1
    while True:
        params = dict(pageNo=page, numOfRows=PAGE, MobileOS="ETC", MobileApp="traveltrend",
                      _type="json", startYmd=start, endYmd=end)
        cache = CACHE / "visitors" / f"{start}_{end}_p{page}.json"
        body = fetch_cached(API, int(VISITOR_DAILY_LIMIT * LIMIT_MARGIN), URL, params, cache)["response"]["body"]
        if page * PAGE >= int(body["totalCount"]):
            return
        page += 1


def main():
    try:
        for start, end in month_ranges():
            fetch_range(start, end)
            print("완료", start, end, flush=True)
    except QuotaExceeded as e:
        print(e)


if __name__ == "__main__":
    main()
