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
