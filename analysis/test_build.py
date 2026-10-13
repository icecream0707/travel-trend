"""build.py 의 순수 함수 자체 점검. 실행: python analysis/test_build.py (assert 만 사용, 외부 의존 없음)"""
from build import (classify_tercile, crosswalk_old_to_new, drop_children, is_alert, make_text,
                   month_list, sido_label, yoy)

# 3분위 분류: 경계값과 같으면 '비슷'
assert [classify_tercile(v, 3, 7) for v in (2, 3, 5, 7, 8)] == [0, 1, 1, 1, 2]

# 표시 규칙: 기본(extreme_jump)은 적음↔많음만, any_change 는 달라지기만 하면
assert is_alert(0, 2, "extreme_jump") and is_alert(2, 0, "extreme_jump")
assert not is_alert(0, 1, "extreme_jump") and not is_alert(1, 1, "extreme_jump")
assert is_alert(0, 1, "any_change") and not is_alert(1, 1, "any_change")

# 변화율: 전년이 0 이면 계산 불가
assert yoy(110, 100) == 10 and yoy(5, 0) is None

# 하위 구 제거: 상위 시가 있으면 구를 빼고, 서울 구처럼 상위가 없으면 남긴다
assert drop_children({"41110", "41111", "41113", "11110", "11140"}) == {"41110", "11110", "11140"}

# 개편 연결: 이름이 12xxx 안에서 유일하면 연결, 인천 구는 연결하지 않음
old = {"46110": "목포시", "29110": "동구", "28110": "중구"}
new = {"12110": "목포시", "12210": "동구", "28125": "제물포구"}
assert crosswalk_old_to_new(old, new) == {"46110": "12110", "29110": "12210"}

assert sido_label("12210") == "광주" and sido_label("12110") == "전남" and sido_label("41110") == "경기"
assert month_list("202409", "202411") == ["202409", "202410", "202411"]

# 문구: 긍정/부정 단정 없이 '가능성'만, 관측소 없으면 판단 불가
w = {"rainDays": {"prev": 2, "cur": 12, "prevClass": 0, "curClass": 2, "lo": 4, "hi": 8, "alert": True},
     "rainMm": {"prev": 10, "cur": 50, "prevClass": 0, "curClass": 1, "lo": 20, "hi": 90, "alert": False}}
t = make_text("202607", -12.3, 5, 200, w, True)
assert "영향을 미쳤을 가능성" in t and "강수일수" in t and "월강수량" not in t
assert "날씨 판단 불가" in make_text("202607", 3.0, 1, 200, None, False)
print("ok")
