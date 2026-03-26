from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from price_review.analysis import build_excel_bytes, review_quote, review_upload, safe_pct_change
from price_review.db import get_master_dataframe, get_summary, get_timeseries_dataframe, rebuild_database
from price_review.parser import parse_report_month


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PRICE_REVIEW_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "material_prices.sqlite"
UPLOADED_PDF_DIR = DATA_DIR / "uploaded_pdfs"


st.set_page_config(page_title="자재 단가 검토 시스템", layout="wide")


def collect_pdf_paths() -> list[Path]:
    base_pdfs = sorted(BASE_DIR.glob("*.pdf"))
    uploaded_pdfs = sorted(UPLOADED_PDF_DIR.glob("*.pdf"))
    selected_by_name: dict[str, Path] = {}

    for pdf_path in base_pdfs:
        selected_by_name[pdf_path.name] = pdf_path

    for pdf_path in uploaded_pdfs:
        selected_by_name[pdf_path.name] = pdf_path

    return sorted(
        selected_by_name.values(),
        key=lambda path: (parse_report_month(path), path.name),
    )


def save_uploaded_pdfs(uploaded_files: list[st.runtime.uploaded_file_manager.UploadedFile]) -> list[Path]:
    UPLOADED_PDF_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for uploaded_file in uploaded_files:
        file_name = Path(uploaded_file.name).name
        parse_report_month(Path(file_name))
        target_path = UPLOADED_PDF_DIR / file_name
        target_path.write_bytes(uploaded_file.getbuffer())
        saved_paths.append(target_path)

    return saved_paths


def ensure_database(force_rebuild: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADED_PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths = collect_pdf_paths()
    if force_rebuild or not DB_PATH.exists():
        rebuild_database(DB_PATH, pdf_paths)


def format_item_label(row: pd.Series) -> str:
    variant = row["variant"] if row["variant"] else "기본"
    return f"{row['section_name']} | {row['spec']} | {variant}"


def display_currency(value: float | None, unit: str = "m") -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:,.0f} 원/{unit}"


def render_sidebar(pdf_paths: list[Path]) -> None:
    summary = get_summary(DB_PATH)
    st.sidebar.title("데이터 상태")
    st.sidebar.write(f"PDF 파일 {len(pdf_paths)}건")
    st.sidebar.write(f"기준월 {summary['first_month']} ~ {summary['last_month']}")
    st.sidebar.write(f"자재 항목 {summary['material_count']}건")
    st.sidebar.write(f"가격 레코드 {summary['price_count']}건")

    if st.sidebar.button("DB 다시 구축", use_container_width=True):
        ensure_database(force_rebuild=True)
        st.cache_data.clear()
        st.rerun()

    st.sidebar.caption("반영 대상 PDF")
    for pdf_path in pdf_paths:
        location = "업로드본" if pdf_path.is_relative_to(UPLOADED_PDF_DIR) else "기본본"
        st.sidebar.code(f"{parse_report_month(pdf_path)} | {location} | {pdf_path.name}", language=None)

    st.sidebar.caption("동일 파일명이 겹치면 업로드본이 우선 적용됩니다.")


@st.cache_data(show_spinner=False)
def load_master_df() -> pd.DataFrame:
    ensure_database()
    master_df = get_master_dataframe(DB_PATH)
    master_df["variant_display"] = master_df["variant"].replace("", "기본")
    master_df["item_label"] = master_df.apply(format_item_label, axis=1)
    master_df["official_yoy_pct"] = master_df.apply(
        lambda row: safe_pct_change(row["latest_price"], row["previous_price"]),
        axis=1,
    )
    return master_df


@st.cache_data(show_spinner=False)
def load_timeseries(item_codes: tuple[str, ...]) -> pd.DataFrame:
    timeseries_df = get_timeseries_dataframe(DB_PATH, list(item_codes))
    if timeseries_df.empty:
        return timeseries_df
    timeseries_df["item_label"] = timeseries_df.apply(format_item_label, axis=1)
    return timeseries_df


def build_template_frames(master_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    template_df = pd.DataFrame(
        columns=["item_code", "section_name", "spec", "variant", "quoted_price", "note"]
    )
    instructions = pd.DataFrame(
        {
            "guide": [
                "권장 방식은 item_code + quoted_price 입력입니다.",
                "item_code가 없으면 section_name, spec, variant를 정확히 입력해야 합니다.",
                "quoted_price는 숫자만 입력하면 됩니다.",
            ]
        }
    )
    master_export = master_df[
        [
            "item_code",
            "section_name",
            "spec",
            "variant",
            "unit",
            "latest_month",
            "latest_price",
            "previous_month",
            "previous_price",
        ]
    ].copy()
    return template_df, instructions, master_export


def render_pdf_input_tab(pdf_paths: list[Path]) -> None:
    st.subheader("PDF 입력 및 DB 갱신")
    st.write("파일 선택창에서 PDF를 고른 뒤 `실행`을 누르면 저장 후 DB를 갱신합니다.")
    uploaded_pdfs = st.file_uploader(
        "PDF 선택",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_input_files",
    )

    if uploaded_pdfs:
        st.caption("선택된 파일")
        for uploaded_pdf in uploaded_pdfs:
            st.write(f"- {uploaded_pdf.name}")

    if st.button("실행", type="primary", use_container_width=True):
        if not uploaded_pdfs:
            st.warning("먼저 반영할 PDF를 선택해 주세요.")
        else:
            try:
                with st.spinner("PDF 저장 및 DB 갱신 중입니다."):
                    saved_paths = save_uploaded_pdfs(uploaded_pdfs)
                    ensure_database(force_rebuild=True)
                    st.cache_data.clear()
            except ValueError:
                st.error("파일명에서 기준월을 읽을 수 없습니다. 예: 202604_1075.pdf 형식으로 올려 주세요.")
            else:
                months = ", ".join(sorted(parse_report_month(path) for path in saved_paths))
                summary = get_summary(DB_PATH)
                st.success(
                    f"{len(saved_paths)}건 저장 후 DB를 갱신했습니다. "
                    f"반영 기준월: {months} / 자재 {summary['material_count']}건 / 가격 {summary['price_count']}건"
                )
                st.rerun()

    st.divider()
    st.caption("현재 DB 반영 대상")
    tracked_df = pd.DataFrame(
        [
            {
                "기준월": parse_report_month(pdf_path),
                "파일명": pdf_path.name,
                "반영 우선순위": "업로드본" if pdf_path.is_relative_to(UPLOADED_PDF_DIR) else "기본본",
            }
            for pdf_path in pdf_paths
        ]
    )
    st.dataframe(tracked_df, use_container_width=True, hide_index=True)


def render_trend_tab(master_df: pd.DataFrame) -> None:
    st.subheader("가격 추이")
    if master_df.empty:
        st.info("DB에 분석 가능한 자재 데이터가 없습니다. PDF 입력 후 다시 실행해 주세요.")
        return

    options = master_df["item_label"].tolist()
    default_items = options[:2] if len(options) >= 2 else options
    selected_labels = st.multiselect(
        "비교할 자재를 선택하세요. 최대 2개까지 동시에 볼 수 있습니다.",
        options=options,
        default=default_items,
        max_selections=2,
    )

    if not selected_labels:
        st.info("자재를 선택하면 연도별 가격 추이가 표시됩니다.")
        return

    selected_df = master_df[master_df["item_label"].isin(selected_labels)].copy()
    timeseries_df = load_timeseries(tuple(selected_df["item_code"].tolist()))

    chart = px.line(
        timeseries_df,
        x="report_month",
        y="price",
        color="item_label",
        markers=True,
        title="공표 단가 추이",
        labels={"report_month": "기준월", "price": "단가(원)", "item_label": "자재"},
    )
    st.plotly_chart(chart, use_container_width=True)

    metric_columns = st.columns(len(selected_df))
    for column, (_, row) in zip(metric_columns, selected_df.iterrows()):
        delta_text = (
            f"{row['official_yoy_pct']:.2f}%"
            if pd.notna(row["official_yoy_pct"])
            else "이전 연도 데이터 없음"
        )
        column.metric(
            label=row["item_label"],
            value=display_currency(row["latest_price"], row["unit"]),
            delta=delta_text,
        )

    display_df = selected_df[
        [
            "section_name",
            "spec",
            "variant_display",
            "latest_month",
            "latest_price",
            "previous_month",
            "previous_price",
            "official_yoy_pct",
        ]
    ].rename(
        columns={
            "section_name": "자재",
            "spec": "규격",
            "variant_display": "구분",
            "latest_month": "최신 기준월",
            "latest_price": "최신 단가",
            "previous_month": "이전 기준월",
            "previous_price": "이전 단가",
            "official_yoy_pct": "1년 변동률(%)",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_manual_review_tab(master_df: pd.DataFrame) -> None:
    st.subheader("수동 입력 단가 검토")
    if master_df.empty:
        st.info("DB에 검토 가능한 자재 데이터가 없습니다. PDF 입력 후 다시 실행해 주세요.")
        return

    sections = master_df["section_name"].drop_duplicates().tolist()
    selected_section = st.selectbox("자재 분류", sections)

    section_df = master_df[master_df["section_name"] == selected_section]
    selected_spec = st.selectbox("규격", section_df["spec"].drop_duplicates().tolist())

    spec_df = section_df[section_df["spec"] == selected_spec].copy()
    spec_df["variant_display"] = spec_df["variant"].replace("", "기본")
    selected_variant_display = st.selectbox("심수/전압 구분", spec_df["variant_display"].tolist())

    item_row = spec_df[spec_df["variant_display"] == selected_variant_display].iloc[0]
    quoted_price = st.number_input(
        "검토할 입력 단가(원)",
        min_value=0.0,
        step=100.0,
        value=float(item_row["latest_price"]) if pd.notna(item_row["latest_price"]) else 0.0,
    )

    result = review_quote(item_row, quoted_price)
    st.write(f"선택 자재: `{item_row['section_name']} / {item_row['spec']} / {item_row['variant_display']}`")

    metric_columns = st.columns(4)
    metric_columns[0].metric("최신 공표단가", display_currency(result["latest_price"], item_row["unit"]))
    metric_columns[1].metric("입력 단가", display_currency(result["quoted_price"], item_row["unit"]))
    metric_columns[2].metric("입력 대비 판정", result["quote_gap_text"])
    yoy_text = (
        f"{result['official_yoy_pct']:.2f}%"
        if result["official_yoy_pct"] is not None
        else "이전 연도 데이터 없음"
    )
    metric_columns[3].metric("공표단가 1년 변동률", yoy_text)

    quote_gap_pct = result["quote_gap_pct"]
    if quote_gap_pct is None:
        st.warning("최신 공표단가가 없어 비교할 수 없습니다.")
    elif quote_gap_pct > 0:
        st.error(f"입력 단가는 최신 공표단가 대비 {abs(quote_gap_pct):.2f}% 비쌉니다.")
    elif quote_gap_pct < 0:
        st.success(f"입력 단가는 최신 공표단가 대비 {abs(quote_gap_pct):.2f}% 저렴합니다.")
    else:
        st.info("입력 단가는 최신 공표단가와 동일합니다.")

    timeseries_df = load_timeseries((item_row["item_code"],))
    if not timeseries_df.empty:
        chart = px.line(
            timeseries_df,
            x="report_month",
            y="price",
            markers=True,
            title="선택 자재 가격 추이",
            labels={"report_month": "기준월", "price": "단가(원)"},
        )
        chart.add_scatter(
            x=[item_row["latest_month"]],
            y=[quoted_price],
            mode="markers",
            marker={"size": 12, "symbol": "diamond"},
            name="입력 단가",
        )
        st.plotly_chart(chart, use_container_width=True)


def render_upload_tab(master_df: pd.DataFrame) -> None:
    st.subheader("엑셀 업로드 단가 검토")
    if master_df.empty:
        st.info("DB에 검토 기준 데이터가 없습니다. 먼저 PDF를 반영해 주세요.")
        return

    template_df, instructions_df, master_export = build_template_frames(master_df)
    template_bytes = build_excel_bytes(
        [
            ("input_template", template_df),
            ("instructions", instructions_df),
            ("master_items", master_export),
        ]
    )
    st.download_button(
        "업로드 템플릿 다운로드",
        data=template_bytes,
        file_name="price_review_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    uploaded_file = st.file_uploader("엑셀 또는 CSV 파일 업로드", type=["xlsx", "xls", "csv"])

    if not uploaded_file:
        st.info("템플릿을 내려받아 단가를 입력한 뒤 업로드하면 일괄 검토됩니다.")
        return

    uploaded_df = (
        pd.read_csv(uploaded_file)
        if uploaded_file.name.lower().endswith(".csv")
        else pd.read_excel(uploaded_file)
    )

    try:
        result_df = review_upload(master_df, uploaded_df)
    except ValueError as error:
        st.error(str(error))
        return

    if result_df.empty:
        st.info("검토할 데이터가 없습니다. quoted_price와 자재 식별값을 입력해 주세요.")
        return

    matched_count = int((result_df["match_status"] == "matched").sum())
    total_count = len(result_df)
    missing_count = total_count - matched_count
    metric_columns = st.columns(3)
    metric_columns[0].metric("업로드 건수", f"{total_count}건")
    metric_columns[1].metric("매칭 성공", f"{matched_count}건")
    metric_columns[2].metric("매칭 실패", f"{missing_count}건")

    display_df = result_df.rename(
        columns={
            "item_code": "자재코드",
            "section_name": "자재",
            "spec": "규격",
            "variant": "구분",
            "quoted_price": "입력 단가",
            "latest_month": "최신 기준월",
            "latest_price": "최신 단가",
            "previous_month": "이전 기준월",
            "previous_price": "이전 단가",
            "quote_gap_pct": "최신 대비 차이(%)",
            "official_yoy_pct": "공표단가 1년 변동률(%)",
            "review_result": "판정",
            "match_status": "매칭 상태",
            "note": "비고",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    result_bytes = build_excel_bytes([("review_result", display_df)])
    st.download_button(
        "검토 결과 다운로드",
        data=result_bytes,
        file_name="price_review_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def render_master_tab(master_df: pd.DataFrame) -> None:
    st.subheader("DB 적재 결과")
    if master_df.empty:
        st.info("현재 적재된 자재 데이터가 없습니다.")
        return

    display_df = master_df[
        [
            "item_code",
            "section_name",
            "spec",
            "variant_display",
            "unit",
            "latest_month",
            "latest_price",
            "previous_month",
            "previous_price",
            "official_yoy_pct",
        ]
    ].rename(
        columns={
            "item_code": "자재코드",
            "section_name": "자재",
            "spec": "규격",
            "variant_display": "구분",
            "unit": "단위",
            "latest_month": "최신 기준월",
            "latest_price": "최신 단가",
            "previous_month": "이전 기준월",
            "previous_price": "이전 단가",
            "official_yoy_pct": "1년 변동률(%)",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def main() -> None:
    ensure_database()
    pdf_paths = collect_pdf_paths()
    master_df = load_master_df()
    render_sidebar(pdf_paths)

    st.title("자재 단가 검토 시스템")
    st.caption("PDF 입력, DB 갱신, 가격 추이 분석, 수동 검토, 엑셀 일괄 검토를 지원합니다.")
    if master_df.empty:
        st.warning("현재 반영된 PDF에서 분석 가능한 가격표를 찾지 못했습니다. 지원되는 PDF 형식인지 확인해 주세요.")

    pdf_tab, trend_tab, manual_tab, upload_tab, master_tab = st.tabs(
        ["PDF 입력", "가격 추이", "수동 검토", "엑셀 업로드", "DB 현황"]
    )
    with pdf_tab:
        render_pdf_input_tab(pdf_paths)
    with trend_tab:
        render_trend_tab(master_df)
    with manual_tab:
        render_manual_review_tab(master_df)
    with upload_tab:
        render_upload_tab(master_df)
    with master_tab:
        render_master_tab(master_df)


if __name__ == "__main__":
    main()
