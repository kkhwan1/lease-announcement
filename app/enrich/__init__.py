"""건물 정보 보강(enrich) 패키지.

PDF에서 추출하지 못한 물리 스펙 필드를 외부 공공데이터 API로 채운다.
주요 보강 소스: 건축물대장(kk_real_estate), 지오코딩 등.

사용 예시:
    from app.enrich import BuildingRegisterEnricher, apply_enrichers

    enrichers = [BuildingRegisterEnricher()]
    b = apply_enrichers(b, enrichers)
"""
from app.enrich.base import Enricher, apply_enrichers
from app.enrich.building_register import BuildingRegisterEnricher

__all__ = ["Enricher", "apply_enrichers", "BuildingRegisterEnricher"]
