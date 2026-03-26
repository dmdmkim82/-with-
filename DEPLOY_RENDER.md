# Render 배포 가이드

이 앱은 업로드한 PDF와 SQLite DB를 계속 저장해야 하므로 `Persistent Disk`가 있는 Render 배포를 기준으로 정리했다.

## 사전 준비

1. 이 폴더를 Git 저장소로 만들고 GitHub에 올린다.
2. Render 계정을 만든다.
3. GitHub 저장소와 Render를 연결한다.

## 배포 방법

1. Render 대시보드에서 `New +` → `Blueprint`를 선택한다.
2. 이 프로젝트가 들어있는 GitHub 저장소를 선택한다.
3. 루트의 `render.yaml`을 읽게 한다.
4. 서비스 이름, 요금제, 도메인을 확인하고 생성한다.

## 현재 설정

- Web Service 이름: `material-price-review`
- 리전: `singapore`
- 런타임: `python`
- 시작 명령: `python -m streamlit run app.py --server.address 0.0.0.0 --server.port $PORT`
- 영구 디스크 마운트 경로: `/opt/render/project/src/data`
- 앱 데이터 경로 환경변수: `PRICE_REVIEW_DATA_DIR=/opt/render/project/src/data`

## 운영 메모

- 루트의 PDF는 초기 기준 데이터로 함께 배포된다.
- 앱에서 새 PDF를 업로드하면 영구 디스크 아래 `data/uploaded_pdfs/`에 저장된다.
- SQLite DB는 `data/material_prices.sqlite`에 저장된다.
- 같은 파일명이 다시 업로드되면 업로드본이 우선 적용된다.

## 로컬 Git 시작 예시

```powershell
git init
git add .
git commit -m "Prepare deployment"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repo>.git
git push -u origin main
```
