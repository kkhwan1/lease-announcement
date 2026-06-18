"""C&W 공백없는 주소 정규화 테스트."""
from app.normalize import insert_address_spacing


def test_cnw_spaceless_address():
    # 시 + 구가 붙은 C&W 형식
    assert insert_address_spacing("서울특별시종로구율곡로 2길19") == "서울특별시 종로구 율곡로 2길19"


def test_already_spaced_passthrough():
    # 오스카 형식(이미 공백) — 변형 없음
    assert insert_address_spacing("서울특별시 강남구 강남대로 374") == "서울특별시 강남구 강남대로 374"


def test_seoul_seocho_spaceless():
    assert insert_address_spacing("서울서초구서초대로 396") == "서울 서초구 서초대로 396"


def test_none_safe():
    assert insert_address_spacing(None) is None


def test_seoul_si_spaceless():
    # '서울시'(특별시 축약) + 구
    assert insert_address_spacing("서울시성동구뚝섬로17가길49") == "서울시 성동구 뚝섬로17가길49"
    assert insert_address_spacing("서울시은평구통일로861") == "서울시 은평구 통일로861"


def test_metro_district_not_over_split():
    # 도로명의 '달구'를 구로 오인하면 안 됨 — '수성구'만 분리
    assert insert_address_spacing("대구광역시수성구달구벌대로2424") == "대구광역시 수성구 달구벌대로2424"
    # '시청로'의 '시'를 구로 오인하면 안 됨 — '서구'만 분리
    assert insert_address_spacing("광주광역시서구시청로30") == "광주광역시 서구 시청로30"
