from __future__ import annotations

from io import BytesIO
from typing import Iterable

import pandas as pd


def safe_pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return ((current - base) / base) * 100.0


def format_gap_text(gap_pct: float | None) -> str:
    if gap_pct is None:
        return "비교 불가"
    if gap_pct > 0:
        return f"{abs(gap_pct):.2f}% 비쌈"
    if gap_pct < 0:
        return f"{abs(gap_pct):.2f}% 저렴"
    return "공식단가와 동일"


def review_quote(item_row: pd.Series, quoted_price: float) -> dict[str, float | str | None]:
    latest_price = to_optional_float(item_row.get("latest_price"))
    previous_price = to_optional_float(item_row.get("previous_price"))
    quote_gap_pct = safe_pct_change(quoted_price, latest_price)
    official_yoy_pct = safe_pct_change(latest_price, previous_price)

    return {
        "quoted_price": quoted_price,
        "latest_month": item_row.get("latest_month"),
        "latest_price": latest_price,
        "previous_month": item_row.get("previous_month"),
        "previous_price": previous_price,
        "quote_gap_pct": quote_gap_pct,
        "official_yoy_pct": official_yoy_pct,
        "quote_gap_text": format_gap_text(quote_gap_pct),
    }


def review_upload(master_df: pd.DataFrame, uploaded_df: pd.DataFrame) -> pd.DataFrame:
    normalized_upload = normalize_uploaded_frame(uploaded_df)
    key_columns = [column for column in ["item_code", "section_name", "spec", "variant"] if column in normalized_upload.columns]
    normalized_upload = normalized_upload.dropna(subset=["quoted_price"], how="all")
    if key_columns:
        normalized_upload = normalized_upload.loc[
            normalized_upload[key_columns].notna().any(axis=1) | normalized_upload["quoted_price"].notna()
        ]
    if normalized_upload.empty:
        return pd.DataFrame(columns=["item_code", "section_name", "spec", "variant", "quoted_price"])

    normalized_upload = normalized_upload.reset_index(drop=True)
    normalized_upload["_row_id"] = normalized_upload.index
    master_lookup = master_df.copy()
    master_lookup["item_code"] = master_lookup["item_code"].astype(str).str.strip().str.upper()
    master_lookup["section_name"] = master_lookup["section_name"].astype(str).str.strip()
    master_lookup["spec"] = master_lookup["spec"].astype(str).str.strip().str.upper()
    master_lookup["variant"] = master_lookup["variant"].fillna("").astype(str).str.strip().str.upper()

    frames: list[pd.DataFrame] = []
    if "item_code" in normalized_upload.columns and normalized_upload["item_code"].notna().any():
        with_code = normalized_upload.loc[normalized_upload["item_code"].notna()].copy()
        code_merged = with_code.merge(master_lookup, how="left", on="item_code", suffixes=("", "_master"))
        frames.append(fill_master_columns(code_merged))

    without_code = normalized_upload.loc[
        normalized_upload["item_code"].isna() if "item_code" in normalized_upload.columns else normalized_upload.index == normalized_upload.index
    ].copy()
    if not without_code.empty:
        required = {"section_name", "spec", "variant"}
        missing = required - set(without_code.columns)
        if missing:
            raise ValueError("업로드 파일에 item_code 또는 section_name/spec/variant 컬럼이 필요합니다.")
        field_merged = without_code.merge(
            master_lookup,
            how="left",
            on=["section_name", "spec", "variant"],
            suffixes=("", "_master"),
        )
        frames.append(fill_master_columns(field_merged))

    if not frames:
        raise ValueError("업로드 파일에 item_code 또는 section_name/spec/variant 컬럼이 필요합니다.")

    merged = pd.concat(frames, ignore_index=True).sort_values("_row_id").reset_index(drop=True)

    merged["quoted_price"] = pd.to_numeric(merged["quoted_price"], errors="coerce")
    merged["latest_price"] = pd.to_numeric(merged["latest_price"], errors="coerce")
    merged["previous_price"] = pd.to_numeric(merged["previous_price"], errors="coerce")
    merged["quote_gap_pct"] = ((merged["quoted_price"] - merged["latest_price"]) / merged["latest_price"]) * 100.0
    merged["official_yoy_pct"] = ((merged["latest_price"] - merged["previous_price"]) / merged["previous_price"]) * 100.0

    merged["match_status"] = merged["latest_price"].apply(lambda value: "matched" if pd.notna(value) else "not_found")
    merged["review_result"] = merged["quote_gap_pct"].apply(format_gap_text)
    merged.loc[merged["match_status"] == "not_found", "review_result"] = "매칭 실패"

    output_columns = [
        column
        for column in [
            "item_code",
            "section_name",
            "spec",
            "variant",
            "quoted_price",
            "latest_month",
            "latest_price",
            "previous_month",
            "previous_price",
            "quote_gap_pct",
            "official_yoy_pct",
            "review_result",
            "match_status",
            "note",
        ]
        if column in merged.columns
    ]
    return merged[output_columns]


def normalize_uploaded_frame(uploaded_df: pd.DataFrame) -> pd.DataFrame:
    renamed = uploaded_df.copy()
    renamed.columns = [str(column).strip().lower().replace(" ", "_") for column in renamed.columns]
    aliases = {
        "category": "section_name",
        "section": "section_name",
        "material_name": "section_name",
        "offered_price": "quoted_price",
        "input_price": "quoted_price",
        "price": "quoted_price",
    }
    renamed = renamed.rename(columns=aliases)

    if "item_code" in renamed.columns:
        renamed["item_code"] = normalize_text_series(renamed["item_code"], uppercase=True)
    if "section_name" in renamed.columns:
        renamed["section_name"] = normalize_text_series(renamed["section_name"])
    if "spec" in renamed.columns:
        renamed["spec"] = normalize_text_series(renamed["spec"], uppercase=True)
    if "variant" in renamed.columns:
        renamed["variant"] = normalize_text_series(renamed["variant"], uppercase=True, empty_value="")
    else:
        renamed["variant"] = ""

    if "quoted_price" not in renamed.columns:
        raise ValueError("업로드 파일에 quoted_price 컬럼이 필요합니다.")

    renamed["quoted_price"] = pd.to_numeric(renamed["quoted_price"], errors="coerce")
    return renamed


def build_excel_bytes(sheets: Iterable[tuple[str, pd.DataFrame]]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets:
            dataframe.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buffer.seek(0)
    return buffer.getvalue()


def to_optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fill_master_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    for column in list(dataframe.columns):
        if not column.endswith("_master"):
            continue
        base_column = column.removesuffix("_master")
        if base_column in dataframe.columns:
            dataframe[base_column] = dataframe[base_column].where(dataframe[base_column].notna(), dataframe[column])
        else:
            dataframe[base_column] = dataframe[column]
    drop_columns = [column for column in dataframe.columns if column.endswith("_master")]
    return dataframe.drop(columns=drop_columns)


def normalize_text_series(
    series: pd.Series,
    uppercase: bool = False,
    empty_value: str | pd._libs.missing.NAType | None = pd.NA,
) -> pd.Series:
    normalized = series.where(series.notna(), None).astype("object")
    normalized = normalized.apply(lambda value: str(value).strip() if value is not None else None)
    normalized = normalized.replace({"": empty_value, "nan": empty_value, "None": empty_value, "NONE": empty_value})
    if uppercase:
        normalized = normalized.apply(lambda value: value.upper() if isinstance(value, str) else value)
    return normalized
