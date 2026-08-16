type SkeletonProps = {
  className?: string;
};

/**
 * 로딩 중 자리를 잡아두는 회색 블록. 크기는 호출부가 className으로 준다.
 *
 * animate-pulse는 opacity만 건드려 컴포지터에서 처리된다. 모션 최소화에서는
 * globals.css의 전역 규칙(117~125행)이 애니메이션을 멈춘다 — 여기서 따로
 * 처리하지 않는다.
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return <div aria-hidden className={`animate-pulse rounded bg-foreground/[0.07] ${className}`} />;
}

type SkeletonListProps = {
  rows?: number;
  /** 행 하나의 높이. 그 자리에 올 실제 콘텐츠와 비슷하게 준다 */
  rowClassName?: string;
  className?: string;
  /** 스크린리더가 읽을 문구 */
  label?: string;
};

/**
 * 목록 자리를 잡는 스켈레톤.
 *
 * role="status"와 aria-label이 반드시 필요하다. 이전의 "불러오는 중..."은
 * 글자라서 스크린리더가 읽었는데, 순수 시각 블록으로 바꾸면 그 알림이
 * 사라진다. 눈으로 보는 사람만 상태를 알게 되는 건 후퇴다.
 */
export function SkeletonList({
  rows = 3,
  rowClassName = 'h-14',
  className = '',
  label = '불러오는 중',
}: SkeletonListProps) {
  return (
    <div role="status" aria-label={label} className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`w-full ${rowClassName}`} />
      ))}
    </div>
  );
}
