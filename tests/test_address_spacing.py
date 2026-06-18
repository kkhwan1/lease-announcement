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
