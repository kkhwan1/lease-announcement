export const metadata = {
  title: "서비스 소개 - 오피스 임대매물 검색",
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="mb-6 text-2xl font-bold">서비스 소개</h1>

      <div className="space-y-6 text-ink">
        <section>
          <h2 className="mb-2 text-lg font-semibold">무엇을 제공하나요</h2>
          <p className="text-steel">
            서울 주요 권역의 오피스 임대매물 정보를 한곳에 모아 지도와 목록으로
            제공합니다. 건물별 기본 정보, 층별 공실 현황, 평당 임대료와 관리비,
            건축물대장 정보를 함께 확인할 수 있습니다.
          </p>
        </section>

        <section>
          <h2 className="mb-2 text-lg font-semibold">데이터 출처</h2>
          <p className="text-steel">
            여러 중개사(C&amp;W, 오스카, 에스원 등)가 공개한 임대 안내문을
            취합하고, 국토교통부 건축물대장 정보로 건물 기본 정보를 보완합니다.
            매월 갱신되며, 갱신 시점의 정보가 누적되어 임대료 추이를 확인할 수
            있습니다.
          </p>
        </section>

        <section>
          <h2 className="mb-2 text-lg font-semibold">유의사항</h2>
          <p className="text-steel">
            본 서비스는 정보 제공을 목적으로 하며 중개 행위가 아닙니다. 실제 공실
            여부와 계약 조건은 시점에 따라 달라질 수 있으므로, 계약 전 반드시
            해당 건물 및 중개사를 통해 별도로 확인하시기 바랍니다.
          </p>
        </section>
      </div>
    </div>
  );
}
