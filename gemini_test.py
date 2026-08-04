import google.generativeai as genai

# 내 API 키 입력
GOOGLE_API_KEY = "AIzaSyAobduK-HnSUtFfJKmQRayB9rrF9yXkJuc"
genai.configure(api_key=GOOGLE_API_KEY)

print("— 사용 가능한 모델 목록 —")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(m.name)
