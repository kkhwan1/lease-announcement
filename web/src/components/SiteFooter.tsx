export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-6 text-sm text-muted">
        <p>
          본 서비스는 공개된 임대 안내문과 공공 건축물대장 정보를 취합해 제공하는
          정보 제공 목적의 서비스입니다. 중개 행위가 아니며, 실제 계약 조건은
          반드시 별도 확인이 필요합니다.
        </p>
        <p className="mt-2">
          데이터 출처: 중개사 임대안내문(C&amp;W·오스카·에스원) + 국토교통부
          건축물대장
        </p>
      </div>
    </footer>
  );
}
