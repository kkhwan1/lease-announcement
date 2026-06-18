"""좌표 보강 테스트 (네트워크 모킹)."""
from unittest.mock import patch, MagicMock

from app.geocode import geocode_kakao, GeoPoint


def test_geocode_kakao_success():
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "documents": [{"x": "127.0276", "y": "37.4979"}]
    }
    with patch("app.geocode.httpx.get", return_value=fake):
        pt = geocode_kakao("서울특별시 강남구 강남대로 374", api_key="dummy")
    assert pt == GeoPoint(lat=37.4979, lng=127.0276)


def test_geocode_kakao_no_result():
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {"documents": []}
    with patch("app.geocode.httpx.get", return_value=fake):
        pt = geocode_kakao("없는주소", api_key="dummy")
    assert pt is None
