"""수집한 원본(cache/)을 읽어 프론트용 분석 결과 JSON(site/public/data/data.json)을 만든다.

흐름
 1) 방문수요: 일 단위(외지인+외국인) → 시군구·월 합산
 2) 시군구 코드 정리: 2026-07 개편 코드 연결, 하위 구 제거, 24개월 전부 있는 시군구만 남김
 3) 전년 동월대비 변화율, 당해 12개월 합계 하위 20% 제외, 월별 순위
 4) 날씨: ASOS 일자료 → 관측소·월 강수일수/월강수량 → 평년(1991~2020) 3분위 → 전년·올해 비교
 5) 해석 문구(규칙 기반 템플릿)
"""
import calendar
import json
from collections import defaultdict
from datetime import datetime

import numpy as np

from api import items_of
from config import (ALERT_MODE, BASELINE_FIRST_YEAR, BASELINE_LAST_YEAR, CACHE, END_YMD,
                    EXCLUDE_BOTTOM_RATIO, MIN_BASELINE_YEARS, OUT, RAIN_DAY_MM, START_YMD)
from stations import STATIONS, map_stations

TOURIST_KINDS = {"2", "3"}   # 외지인(2), 외국인(3). 현지인(1)은 주민이라 제외
CLASS_NAMES = ["적음", "비슷", "많음"]

# 시군구 코드 앞 두 자리 → 시도명 (12xxx 는 광주·전남 통합 코드라 아래 sido_label 에서 따로 나눈다)
SIDO = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "30": "대전", "31": "울산", "36": "세종",
        "41": "경기", "43": "충북", "44": "충남", "47": "경북", "48": "경남", "50": "제주", "51": "강원",
        "52": "전북"}


# ───────────────────────── 순수 함수 (test_build.py 에서 검증) ─────────────────────────

def sido_label(code: str) -> str:
    """시군구코드로 시도명을 구한다. 12xxx 중 122xx~123xx 는 광주 자치구, 나머지는 전남."""
    if code.startswith("12"):
        return "광주" if "12200" <= code < "12400" else "전남"
    return SIDO.get(code[:2], "")


def drop_children(codes) -> set:
    """'수원시(41110)'와 '수원시 장안구(41111)'처럼 상위 시가 같이 있는 하위 구를 뺀다.

    둘 다 쓰면 방문수요가 이중 집계되므로 시 단위만 쓴다. 서울 구처럼 상위가 없으면 그대로 둔다.
    """
    codes = set(codes)
    return {c for c in codes if not (c[-1] != "0" and (c[:4] + "0") in codes)}


def crosswalk_old_to_new(old_names: dict, new_names: dict) -> dict:
    """2026-07 광주·전남 통합 개편 전 코드(29xxx 광주, 46xxx 전남)를 개편 후 12xxx 코드로 잇는다.

    이름이 12xxx 안에서 유일할 때만 연결한다. 인천처럼 구가 새로 쪼개진 곳은 잇지 않고
    이후 '24개월 전부 있는 시군구만' 규칙으로 자동 제외된다.
    """
    by_name = defaultdict(list)
    for c, n in new_names.items():
        if c.startswith("12"):
            by_name[n].append(c)
    out = {}
    for c, n in old_names.items():
        if c[:2] in ("29", "46") and c not in new_names and len(by_name.get(n, [])) == 1:
            out[c] = by_name[n][0]
    return out


def classify_tercile(v: float, lo: float, hi: float) -> int:
    """평년 3분위 경계(lo=하위 1/3, hi=상위 1/3)에 따라 0=적음, 1=비슷, 2=많음."""
    return 0 if v < lo else 2 if v > hi else 1


def is_alert(prev_cls: int, cur_cls: int, mode: str = ALERT_MODE) -> bool:
    """전년과 올해의 평년 구간이 '확연히' 다른가."""
    if mode == "any_change":
        return prev_cls != cur_cls
    return {prev_cls, cur_cls} == {0, 2}     # extreme_jump: 적음↔많음


def yoy(cur: float, prev: float):
    """전년 동월대비 변화율(%). 전년이 0이면 계산할 수 없어 None."""
    return None if not prev else (cur - prev) / prev * 100


def month_list(start_ym: str, end_ym: str) -> list:
    """'202409'~'202608' → ['202409', ..., '202608']"""
    y, m = int(start_ym[:4]), int(start_ym[4:])
    out = []
    while f"{y}{m:02d}" <= end_ym:
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def prev_year(ym: str) -> str:
    return f"{int(ym[:4]) - 1}{ym[4:]}"


# ───────────────────────── 방문수요 ─────────────────────────

def load_visitors():
    """캐시된 방문자 페이지를 읽어 {(코드, 월): 합계}, {(코드, 월): 날짜 집합}, {코드: 이름} 을 만든다."""
    total = defaultdict(float)
    days = defaultdict(set)
    names = {}   # 가장 늦은 날짜의 이름을 쓴다(파일을 날짜순으로 읽으므로 덮어쓰면 마지막이 남는다)
    for f in sorted((CACHE / "visitors").glob("*.json")):
        body = json.loads(f.read_text(encoding="utf8"))["response"]["body"]
        for it in items_of(body):
            ym = it["baseYmd"][:6]
            code = it["signguCode"]
            names[code] = it["signguNm"]
            days[(code, ym)].add(it["baseYmd"])
            if it["touDivCd"] in TOURIST_KINDS:       # 외국인 행이 비는 시군구는 합계에 0으로 반영됨
                total[(code, ym)] += float(it["touNum"])
    return total, days, names


def build_region_months(total, days, names, months):
    """코드 연결·하위 구 제거·완전성 검사를 거친 {코드: {월: 방문수요}} 와 {코드: 이름}."""
    # 개편 전 코드를 새 코드로 연결. 이름은 가장 늦은 기간 기준으로 쓴다.
    latest = {c: n for c, n in names.items() if (c, months[-1]) in days}
    cw = crosswalk_old_to_new(names, latest)

    vis = defaultdict(dict)
    dcount = defaultdict(int)
    for (code, ym), v in total.items():
        new = cw.get(code, code)
        vis[new][ym] = vis[new].get(ym, 0.0) + v
    for (code, ym), ds in days.items():
        new = cw.get(code, code)
        # 개편 전·후 코드가 하루씩 겹치는 달이 있어도 날짜 수가 달 길이를 넘지 않게 합친다
        dcount[(new, ym)] += len(ds)

    ok = set()
    for code in vis:
        if all(ym in vis[code] and dcount[(code, ym)] == calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]
               for ym in months):
            ok.add(code)
    ok = drop_children(ok)
    return {c: vis[c] for c in ok}, {c: latest.get(c) or names[c] for c in ok}


# ───────────────────────── 날씨 ─────────────────────────

def load_asos():
    """캐시된 ASOS 페이지를 읽어 {(지점, 월): {'days': 일수, 'rain_days': n, 'rain_mm': x}} 를 만든다."""
    agg = defaultdict(lambda: {"days": set(), "rain_days": 0, "rain_mm": 0.0})
    for f in (CACHE / "asos").glob("*.json"):
        resp = json.loads(f.read_text(encoding="utf8")).get("response", {})
        for it in items_of(resp.get("body", {})):
            a = agg[(int(it["stnId"]), it["tm"][:7].replace("-", ""))]
            if it["tm"] in a["days"]:
                continue
            a["days"].add(it["tm"])
            mm = float(it["sumRn"]) if it["sumRn"] != "" else 0.0   # 비어 있으면 강수 없음으로 본다
            a["rain_mm"] += mm
            a["rain_days"] += mm >= RAIN_DAY_MM
    return {k: {"days": len(v["days"]), "rain_days": v["rain_days"], "rain_mm": round(v["rain_mm"], 1)}
            for k, v in agg.items()}


def month_complete(asos, stn, ym) -> bool:
    a = asos.get((stn, ym))
    return bool(a) and a["days"] == calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]


def tercile_bounds(asos, stn, month, key):
    """지점·달(01~12)의 평년 기간 값들로 (하위 1/3 경계, 상위 1/3 경계). 유효 연수가 모자라면 None."""
    vals = [asos[(stn, f"{y}{month}")][key] for y in range(BASELINE_FIRST_YEAR, BASELINE_LAST_YEAR + 1)
            if month_complete(asos, stn, f"{y}{month}")]
    if len(vals) < MIN_BASELINE_YEARS:
        return None
    lo, hi = np.percentile(vals, [100 / 3, 200 / 3])
    return float(lo), float(hi)


ATTRS = {"rainDays": ("rain_days", "강수일수", "일"), "rainMm": ("rain_mm", "월강수량", "mm")}
JOSA = {"rainDays": "가", "rainMm": "이"}   # 주격 조사(받침 유무)


def weather_for(asos, stn, ym):
    """한 시군구·한 달의 날씨 비교. 관측소가 없거나 자료가 모자라면 None."""
    pym = prev_year(ym)
    if stn is None or not (month_complete(asos, stn, ym) and month_complete(asos, stn, pym)):
        return None
    out = {}
    for name, (key, _, _) in ATTRS.items():
        b = tercile_bounds(asos, stn, ym[4:], key)
        if b is None:
            return None
        p, c = asos[(stn, pym)][key], asos[(stn, ym)][key]
        pc, cc = classify_tercile(p, *b), classify_tercile(c, *b)
        out[name] = {"prev": p, "cur": c, "prevClass": pc, "curClass": cc,
                     "lo": round(b[0], 1), "hi": round(b[1], 1), "alert": is_alert(pc, cc)}
    return out


# ───────────────────────── 해석 문구 ─────────────────────────

def make_text(ym, yoy_pct, rank, ranked_n, w, has_station):
    """규칙 기반 해석 문구. 날씨 영향의 긍정/부정은 판단하지 않고 '영향을 미쳤을 가능성'까지만 쓴다."""
    y, m = int(ym[:4]), int(ym[4:])
    if yoy_pct is None:
        return f"{y}년 {m}월은 전년 동월 방문수요가 없어 변화율을 계산할 수 없습니다."
    head = (f"{y}년 {m}월 방문수요는 전년 동월보다 {abs(yoy_pct):.1f}% "
            f"{'증가' if yoy_pct >= 0 else '감소'}했고, 변화율 순위는 {ranked_n}곳 중 {rank}위입니다.")
    if not has_station:
        return head + " 이 시군구는 ASOS 관측소가 없어 날씨 판단 불가입니다."
    if w is None:
        return head + " 날씨 자료(평년 기록 또는 해당 월 관측)가 부족해 날씨 판단 불가입니다."
    hits = []
    for name, (_, label, unit) in ATTRS.items():
        a = w[name]
        if a["alert"]:
            hits.append(f"{label}{JOSA[name]} 전년 {a['prev']:g}{unit}({CLASS_NAMES[a['prevClass']]})에서 올해 "
                        f"{a['cur']:g}{unit}({CLASS_NAMES[a['curClass']]})로 평년({a['lo']:g}~{a['hi']:g}{unit}) 대비 "
                        f"확연히 달라졌습니다")
    if not hits:
        return head + " 날씨 변화는 평년 대비 확연하지 않아 관련 가능성을 표시하지 않습니다."
    return (head + " " + ", ".join(hits) + ". 날씨 변화가 방문수요 변화에 영향을 미쳤을 가능성이 있습니다. "
            "다만 인과를 증명하지는 않습니다.")


# ───────────────────────── 조립 ─────────────────────────

def main():
    months24 = month_list(START_YMD[:6], END_YMD[:6])
    months12 = months24[12:]

    total, days, names = load_visitors()
    vis, rnames = build_region_months(total, days, names, months24)

    # 당해(분석 12개월) 방문수요 합계 하위 20% 제외 — 전년에 인기 없다가 뜬 곳도 당해 기준이면 남는다.
    cur_sum = {c: sum(vis[c][m] for m in months12) for c in vis}
    cutoff = np.quantile(list(cur_sum.values()), EXCLUDE_BOTTOM_RATIO)
    kept = {c for c, s in cur_sum.items() if s >= cutoff}

    # 관측소 대응은 제외 대상까지 포함한 전체 시군구로 계산해, '자동 매칭 실패'가 진짜 실패만 가리키게 한다.
    stn_by_region, unmatched = map_stations({c: rnames[c] for c in vis})
    if unmatched:
        print("자동 매칭 안 된 관측소(날씨 판단 불가로 처리):", unmatched)

    asos = load_asos()

    # 24개월이 이어지지 않아(개편 등) 분석에서 빠진 시군구를 눈으로 확인할 수 있게 출력한다.
    latest_codes = drop_children({c for c, n in names.items() if (c, months24[-1]) in days})
    dropped = sorted(latest_codes - set(vis))
    if dropped:
        print("연속성 없어 제외:", [(c, names[c]) for c in dropped])

    # 월별 순위
    rank = {}
    for ym in months12:
        order = sorted(kept, key=lambda c: -(yoy(vis[c][ym], vis[c][prev_year(ym)]) or -1e9))
        for i, c in enumerate(order, 1):
            rank[(c, ym)] = i

    regions = []
    for c in sorted(kept):
        stn = stn_by_region.get(c)
        months = {}
        for ym in months12:
            v, pv = vis[c][ym], vis[c][prev_year(ym)]
            y = yoy(v, pv)
            w = weather_for(asos, stn, ym)
            months[f"{ym[:4]}-{ym[4:]}"] = {
                "v": round(v), "pv": round(pv), "yoy": None if y is None else round(y, 2),
                "rank": rank[(c, ym)], "w": w,
                "alert": bool(w and any(a["alert"] for a in w.values())),
                "text": make_text(ym, y, rank[(c, ym)], len(kept), w, stn is not None),
            }
        regions.append({"code": c, "name": rnames[c], "sido": sido_label(c),
                        "station": {"id": stn, "name": STATIONS[stn]} if stn else None,
                        "months": months})

    OUT.mkdir(parents=True, exist_ok=True)
    data = {"meta": {"months": [f"{m[:4]}-{m[4:]}" for m in months12], "rankedCount": len(kept),
                     "excludedCount": len(vis) - len(kept), "totalRegions": len(vis),
                     "baseline": f"{BASELINE_FIRST_YEAR}~{BASELINE_LAST_YEAR}", "alertMode": ALERT_MODE,
                     "period": f"{START_YMD}~{END_YMD}", "generatedAt": datetime.now().strftime("%Y-%m-%d")},
            "regions": regions}
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    withw = sum(1 for r in regions if r["station"])
    print(f"시군구 {len(vis)}개 중 순위 대상 {len(kept)}개(제외 {len(vis) - len(kept)}), 날씨 분석 가능 {withw}개")


if __name__ == "__main__":
    main()
