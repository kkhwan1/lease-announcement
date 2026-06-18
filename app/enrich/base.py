"""보강(Enricher) 추상 기반 클래스 및 파이프라인 유틸리티.

설계 원칙:
- PDF 추출 값(field_sources='pdf_parse')은 절대 덮어쓰지 않음 — PDF 우선.
- b.missing_fields()가 반환하는 빈 필드만 채우고, 채운 필드에 self.name을 출처로 기록.
- apply_enrichers()는 예외 안전 — 보강 실패해도 원본 b 그대로 반환.
"""
from __future__ import annotations

import logging
import warnings
from abc import ABC, abstractmethod
from typing import Sequence

from app.schemas import BuildingExtraction

logger = logging.getLogger(__name__)


class Enricher(ABC):
    """건물 정보 보강 추상 기반 클래스.

    구현 시 name 클래스 변수와 enrich() 메서드를 정의해야 한다.
    enrich()는 b.missing_fields()를 참고해 자신이 채울 수 있는 필드만 채운다.
    이미 값 있는 필드(field_sources에 등록됐거나 None이 아닌 값)는 건드리지 않는다.
    """

    name: str  # 서브클래스가 반드시 정의 (field_sources 출처 레이블)

    @abstractmethod
    def enrich(self, b: BuildingExtraction) -> BuildingExtraction:
        """BuildingExtraction 보강 후 반환.

        - b.missing_fields() 중 채울 수 있는 것만 채움.
        - 채운 필드마다 b.field_sources[field] = self.name 기록.
        - 실패 시 b를 그대로 반환 (예외를 밖으로 던져도 apply_enrichers가 잡음).
        """
        ...

    def _set_field(self, b: BuildingExtraction, field: str, value: object) -> bool:
        """빈 필드에만 값을 쓰는 헬퍼. 성공 시 True 반환.

        이미 값이 있거나 value가 None이면 쓰지 않는다.
        """
        if value is None:
            return False
        if getattr(b, field, None) is not None:
            # 이미 값 있음 — PDF 우선 정책
            return False
        object.__setattr__(b, field, value)
        b.field_sources[field] = self.name
        return True


def apply_enrichers(
    b: BuildingExtraction,
    enrichers: Sequence[Enricher],
) -> BuildingExtraction:
    """enrichers 목록을 순차 적용해 b를 보강한 결과를 반환.

    - 각 Enricher 실패(예외)는 경고만 남기고 b 그대로 진행 (파이프라인 안 막힘).
    - enrichers가 빈 리스트면 b 그대로 반환.
    """
    for enricher in enrichers:
        try:
            b = enricher.enrich(b)
        except Exception as exc:
            msg = f"[enrich] {enricher.name} 보강 실패 — {type(exc).__name__}: {exc}"
            warnings.warn(msg)
            logger.warning(msg, exc_info=True)
            # b는 보강 전 상태 그대로 유지됨 (enrich 내부에서 b를 수정하다 예외가 날 경우
            # 부분 수정된 b가 남을 수 있으나, 각 Enricher는 _set_field를 통해
            # 원자 단위로 필드를 채우므로 이미 채워진 필드는 유효한 상태임).
    return b
