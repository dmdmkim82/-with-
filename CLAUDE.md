# 작업 규칙

## 가설 조명 계산기 (`가설조명_계산_앱.html`)

- 작업을 마칠 때마다 변경을 PR로 올린 뒤 바로 `main`에 병합해 Vercel 정식 주소에 배포한다(사용자 지시, 2026-11-17).
  - 정식 주소: https://with-mauve.vercel.app
  - Vercel은 `main` 병합 시 자동 배포한다. 병합 전 PR의 Vercel 상태가 성공인지 확인하고, 병합 후 정식 주소가 새 파일을 내보내는지 확인한다.
- Vercel에는 계산기만 정적 페이지로 올린다. `vercel.json`이 빌드 때 계산기를 `public/index.html`로 복사하고, `.vercelignore`가 Streamlit 앱 파일을 업로드에서 뺀다.
- Streamlit 단가 검토 앱(`app.py`)은 Vercel에서 실행되지 않으며 Render(`render.yaml`)로 배포한다.
