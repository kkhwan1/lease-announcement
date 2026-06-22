// 뉴스 소식 페이지 에러 바운더리
"use client";

import { Button } from "@/components/ui/Button";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function NewsError({ reset }: ErrorProps) {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-body-md text-ink">뉴스를 불러오지 못했습니다.</p>
        <Button variant="secondary" size="sm" onClick={reset}>
          다시 시도
        </Button>
      </div>
    </div>
  );
}
