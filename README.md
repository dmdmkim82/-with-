# 자재 단가 검토 시스템

월간 물가 PDF를 SQLite DB로 적재하고, 자재별 가격 추이와 입력 단가를 비교하는 Streamlit 앱이다.

## 기능

- 앱 안에서 PDF 선택 후 DB 갱신
- PDF 자동 파싱 및 DB 적재
- 자재 1~2건 가격 추이 비교
- 드롭다운 기반 수동 단가 검토
- Excel/CSV 업로드 기반 일괄 단가 검토
- 업로드 템플릿 다운로드

## 로컬 실행

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 배포

이 앱은 업로드한 PDF와 SQLite DB를 디스크에 계속 보존해야 하므로 `Render + Persistent Disk` 구성을 권장한다.

- 배포 설정 파일: `render.yaml`
- 배포 가이드: `DEPLOY_RENDER.md`

## 사용 흐름

1. `PDF 입력` 탭에서 파일 선택
2. `실행` 버튼 클릭
3. DB 갱신 완료 후 `가격 추이`, `수동 검토`, `엑셀 업로드` 탭에서 사용

## 입력 기준

- PDF 파일명은 `202604_1075.pdf`처럼 앞에 `YYYYMM`이 있어야 한다.
- 수동 검토: 앱에서 자재 분류, 규격, 구분을 선택하고 단가를 입력
- Excel 업로드: `item_code` + `quoted_price` 조합을 권장
- `item_code`가 없으면 `section_name`, `spec`, `variant`를 정확히 입력해야 매칭된다.

## 부가 도구

- `가설조명_계산_앱.html`: 가설 조명 조도 계산기. 브라우저에서 파일을 바로 열어 쓰는 단독 HTML이다(설치·서버 불필요).
  - 광속법으로 유지 평균조도와 필요개수를 계산하고, 산업안전보건법(안전보건규칙 제8조·제21조)과 화학물질관리법(화학물질안전원고시) 조도 기준 만족 여부를 근거 조문과 함께 표시한다.
  - 등 타입은 조명율표(천장 70%·벽 50%·바닥 20%)에서 고르고, 표에 없는 등은 수동 입력한다. 조명율표·보수율 기준표는 파일 안 스크립트의 `DATA` 객체만 수정하면 된다.
  - Vercel 배포: 저장소를 Vercel에 연결하면 이 계산기만 정적 페이지로 배포된다(사이트 루트 `/`). `vercel.json`이 빌드 때 `public/index.html`로 복사하고, `.vercelignore`가 Streamlit 앱 파일을 업로드에서 제외한다. Streamlit 앱은 Vercel에서 실행되지 않으므로 Render로 배포한다.
