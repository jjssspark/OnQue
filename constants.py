"""계층 간 공유 상수. 어떤 모듈도 import하지 않는다.

값을 실제로 강제하는 쪽과 그 값을 모델에게 힌트로 알려주는 쪽이 서로 다른
모듈에 있는데, 둘을 직접 이으면 import 사이클이 생긴다
(gemini_service ← commitment_service ← assistant_service). 그런 값만 여기 둔다.
"""

# 비서 응답에서 통과시킬 액션 개수 상한. 프론트가 safe 액션을 순차 자동
# 실행하므로, 모델이 할 일 수십 건에 한꺼번에 액션을 내면 클릭 없이 그만큼의
# 쓰기가 나간다. 초과분은 dropped로 합산한다.
#
# assistant_service.validate_actions가 실제로 강제하고,
# gemini_service._ASSISTANT_RESPONSE_SCHEMA가 같은 값을 모델 힌트로 준다.
MAX_ACTIONS = 10
