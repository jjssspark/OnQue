import os

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY 환경변수가 설정되어 있지 않습니다.")
genai.configure(api_key=GOOGLE_API_KEY)

print("— 사용 가능한 모델 목록 —")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(m.name)
