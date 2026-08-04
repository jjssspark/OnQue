# 참고 자료

## page.tsx.variant-a

`onque-backend/onque-frontend/`(잘못된 위치에 중첩돼 있던 사본)에 있던 `app/page.tsx`.
2025-11-19 02:26 작업본. 현재 살아있는 `onque-frontend/app/page.tsx`(03:09 작업본)보다 오래됐으나,
아래 부분은 현재 버전보다 처리가 촘촘해서 참고용으로 남긴다.

- 파일 미선택 시 `alert` 후 `return` 분리 (현재는 `return alert(...)` 한 줄)
- 응답 실패 시 `err?.detail`로 서버 에러 메시지 추출 (현재는 고정 문구)
- `SummaryResponse` 타입 지정 (현재는 `await res.json()` 무타입)

중첩 사본 본체는 삭제됨. 필요한 로직만 골라 현재 파일에 반영할 것.
