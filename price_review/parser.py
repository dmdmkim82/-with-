from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import pdfplumber


SPEC_RE = re.compile(r"\d+(?:\.\d+)?SQ")
VALUE_TOKEN_RE = re.compile(r"^-$|^\d[\d,]*$")
GROUNDING_SECTION_ORDERS = {
    "접지 자재": 20,
    "피뢰 자재": 21,
    "원터치형 접지용구": 22,
}
GROUNDING_COLUMN_RANGES = {
    "left": {
        "item": (70, 132),
        "maker": (132, 154),
        "spec": (154, 250),
        "unit": (250, 266),
        "price": (266, 305),
    },
    "right": {
        "item": (306, 364),
        "maker": (364, 388),
        "spec": (388, 484),
        "unit": (484, 495),
        "price": (495, 535),
    },
}
SECTION_CONFIG = {
    "fgv_tfr_gv": {
        "marker": "(F-GV, TFR-GV)",
        "order": 1,
        "display_name": "0.6/1KV 트레이용 난연비닐절연 접지용전선 (F-GV, TFR-GV)",
    },
    "fw_cv": {
        "marker": "(FW-CV, F-CV, TFR-CV)",
        "order": 2,
        "display_name": "XLPE 절연비닐시스 트레이용 케이블 (FW-CV, F-CV, TFR-CV)",
    },
    "kiv": {
        "marker": "(KIV)",
        "order": 3,
        "display_name": "450/750V 일반용 유연성 단심비닐절연전선 (KIV)",
    },
    "al_tfr_cv": {
        "marker": "(AL-TFR-CV)",
        "order": 4,
        "display_name": "0.6/1KV 알루미늄 CV 전선 (AL-TFR-CV)",
    },
}
FW_CV_VARIANTS = ["LV 1C", "LV 2C", "LV 3C", "LV 4C", "HV 1C", "HV 3C"]
AL_TFR_VARIANTS = ["1C", "2C", "3C", "4C"]
VARIANT_ORDER = {
    "": 0,
    "LV 1C": 1,
    "LV 2C": 2,
    "LV 3C": 3,
    "LV 4C": 4,
    "HV 1C": 5,
    "HV 3C": 6,
    "1C": 1,
    "2C": 2,
    "3C": 3,
    "4C": 4,
}


@dataclass(frozen=True)
class PriceRecord:
    report_month: str
    source_file: str
    section_key: str
    section_name: str
    section_order: int
    spec: str
    spec_value: float
    variant: str
    variant_order: int
    unit: str
    price: float
    detail: str

    @property
    def item_code(self) -> str:
        spec_part = self.spec.replace(".", "_").replace("/", "_").upper()
        variant_part = self.variant.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        parts = [self.section_key.upper(), spec_part]
        if variant_part:
            parts.append(variant_part)
        return "__".join(parts)


@dataclass
class GroundingState:
    category: str = "접지 자재"
    item: str = ""
    maker: str = ""
    spec: str = ""
    unit: str = ""


def parse_pdf(pdf_path: Path | str) -> list[PriceRecord]:
    pdf_path = Path(pdf_path)
    report_month = parse_report_month(pdf_path)
    lines = extract_lines(pdf_path)
    if is_grounding_pdf(lines):
        return parse_grounding_pdf(pdf_path, report_month, lines)

    sections = split_sections(lines)
    records: list[PriceRecord] = []

    for section_key, payload in sections.items():
        config = SECTION_CONFIG[section_key]
        title = payload["title"] or config["display_name"]
        section_lines = payload["lines"]

        if section_key in {"fgv_tfr_gv", "kiv"}:
            records.extend(
                parse_single_price_lines(
                    report_month=report_month,
                    source_file=pdf_path.name,
                    section_key=section_key,
                    section_name=title,
                    section_order=config["order"],
                    lines=section_lines,
                )
            )
        elif section_key == "fw_cv":
            records.extend(
                parse_fw_cv_lines(
                    report_month=report_month,
                    source_file=pdf_path.name,
                    section_name=title,
                    section_order=config["order"],
                    lines=section_lines,
                )
            )
        elif section_key == "al_tfr_cv":
            records.extend(
                parse_al_tfr_cv_lines(
                    report_month=report_month,
                    source_file=pdf_path.name,
                    section_name=title,
                    section_order=config["order"],
                    lines=section_lines,
                )
            )

    return records


def parse_report_month(pdf_path: Path) -> str:
    match = re.search(r"(\d{4})(\d{2})", pdf_path.stem)
    if not match:
        raise ValueError(f"Cannot infer report month from filename: {pdf_path.name}")
    year, month = match.groups()
    return f"{year}-{month}"


def extract_lines(pdf_path: Path) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = normalize_line(raw_line)
                if not line:
                    continue
                lines.append(line)
    return lines


def normalize_line(line: str) -> str:
    line = line.replace("\u2003", " ").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", line)


def is_grounding_pdf(lines: Iterable[str]) -> bool:
    return any("접지 및 피뢰자재" in line for line in lines)


def split_sections(lines: Iterable[str]) -> dict[str, dict[str, str | list[str]]]:
    sections: dict[str, dict[str, str | list[str]]] = {}
    current_key: str | None = None

    for line in lines:
        next_key = detect_section(line)
        if next_key:
            sections.setdefault(next_key, {"title": line, "lines": []})
            current_key = next_key
            continue

        if not current_key:
            continue

        if line.startswith("Data - Information") or "PRINPIA" in line:
            current_key = None
            continue

        sections[current_key]["lines"].append(line)

    return sections


def detect_section(line: str) -> str | None:
    for section_key, config in SECTION_CONFIG.items():
        if config["marker"] in line:
            return section_key
    return None


def parse_grounding_pdf(
    pdf_path: Path,
    report_month: str,
    lines: list[str] | None = None,
) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    order_no = 1

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            row_groups = group_words_by_top(words)
            left_state = GroundingState()
            right_state = GroundingState()

            for row_words in row_groups:
                top = row_words[0]["top"]
                if top < 190 or top > 610:
                    continue

                for side, state in (("left", left_state), ("right", right_state)):
                    record = parse_grounding_record_from_row(
                        row_words=row_words,
                        side=side,
                        state=state,
                        report_month=report_month,
                        source_file=pdf_path.name,
                        order_no=order_no,
                    )
                    if record:
                        records.append(record)
                        order_no += 1

    source_lines = lines if lines is not None else extract_lines(pdf_path)
    records.extend(
        parse_one_touch_grounding_lines(
            report_month=report_month,
            source_file=pdf_path.name,
            lines=source_lines,
            start_order=order_no,
        )
    )

    return deduplicate_records(records)


def group_words_by_top(words: list[dict], tolerance: float = 3.0) -> list[list[dict]]:
    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_top: float | None = None

    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if current_top is None or abs(word["top"] - current_top) <= tolerance:
            current_row.append(word)
            current_top = word["top"] if current_top is None else (current_top + word["top"]) / 2
            continue

        rows.append(sorted(current_row, key=lambda item: item["x0"]))
        current_row = [word]
        current_top = word["top"]

    if current_row:
        rows.append(sorted(current_row, key=lambda item: item["x0"]))

    return rows


def parse_grounding_record_from_row(
    row_words: list[dict],
    side: str,
    state: GroundingState,
    report_month: str,
    source_file: str,
    order_no: int,
) -> PriceRecord | None:
    columns = GROUNDING_COLUMN_RANGES[side]
    item_text = extract_range_text(row_words, *columns["item"])
    maker_text = extract_range_text(row_words, *columns["maker"])
    spec_text = extract_range_text(row_words, *columns["spec"])
    unit_text = extract_range_text(row_words, *columns["unit"])
    price_text = extract_range_text(row_words, *columns["price"])

    category, item_text = strip_grounding_category(item_text, state.category)
    state.category = category

    if not price_text or not is_number_token(price_text):
        return None

    resolved_item = resolve_grounding_item(item_text, state.item)
    resolved_maker = resolve_grounding_field(maker_text, state.maker)
    resolved_spec = resolve_grounding_spec(spec_text, state.spec)
    resolved_unit = resolve_grounding_field(unit_text, state.unit)

    if not resolved_item:
        return None

    state.item = resolved_item
    state.maker = resolved_maker
    state.spec = resolved_spec
    state.unit = resolved_unit

    label_parts = [resolved_item]
    if resolved_maker:
        label_parts.append(resolved_maker)
    if resolved_spec:
        label_parts.append(resolved_spec)
    spec_label = " | ".join(label_parts)

    return PriceRecord(
        report_month=report_month,
        source_file=source_file,
        section_key="grounding",
        section_name=state.category,
        section_order=GROUNDING_SECTION_ORDERS.get(state.category, 99),
        spec=spec_label,
        spec_value=float(order_no),
        variant="",
        variant_order=0,
        unit=resolved_unit,
        price=parse_price(price_text),
        detail=f"item={resolved_item}; maker={resolved_maker}; spec={resolved_spec}",
    )


def parse_one_touch_grounding_lines(
    report_month: str,
    source_file: str,
    lines: list[str],
    start_order: int,
) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    order_no = start_order
    in_section = False
    previous_unit = ""

    for line in lines:
        if line.strip() == "원터치형 접지용구":
            in_section = True
            continue

        if not in_section:
            continue

        if line.startswith("※") or line.startswith("Data - Information") or "PRINPIA" in line:
            break

        if any(token in line for token in ["가격단위", "품 명", "메이커", "단 위", "생산자공표가격"]):
            continue

        tokens = line.split()
        if len(tokens) < 3 or not is_number_token(tokens[-1]):
            continue

        unit = tokens[-2]
        if unit == "〃":
            unit = previous_unit
        previous_unit = unit

        spec_label = " ".join(tokens[:-2]).strip()
        if not spec_label:
            continue

        records.append(
            PriceRecord(
                report_month=report_month,
                source_file=source_file,
                section_key="grounding",
                section_name="원터치형 접지용구",
                section_order=GROUNDING_SECTION_ORDERS["원터치형 접지용구"],
                spec=spec_label,
                spec_value=float(order_no),
                variant="",
                variant_order=0,
                unit=unit,
                price=parse_price(tokens[-1]),
                detail=spec_label,
            )
        )
        order_no += 1

    return records


def extract_range_text(row_words: list[dict], start_x: float, end_x: float) -> str:
    selected_words = []
    for word in row_words:
        center_x = (word["x0"] + word["x1"]) / 2
        if start_x <= center_x < end_x:
            selected_words.append(word["text"])
    return normalize_line(" ".join(selected_words))


def strip_grounding_category(item_text: str, current_category: str) -> tuple[str, str]:
    compact_text = item_text.replace(" ", "")
    if compact_text.startswith("■접지자재"):
        return "접지 자재", normalize_line(item_text.replace("■접 지 자 재", "").replace("■접지자재", ""))
    if compact_text.startswith("■피뢰자재"):
        return "피뢰 자재", normalize_line(item_text.replace("■피 뢰 자 재", "").replace("■피뢰자재", ""))
    return current_category, item_text


def resolve_grounding_item(item_text: str, previous_item: str) -> str:
    if not item_text or item_text == "〃" or item_text.startswith("("):
        return previous_item
    return item_text


def resolve_grounding_field(field_text: str, previous_field: str) -> str:
    if not field_text or field_text == "〃":
        return previous_field
    return field_text


def resolve_grounding_spec(spec_text: str, previous_spec: str) -> str:
    if not spec_text or spec_text == "〃":
        return previous_spec

    if spec_text.startswith("〃"):
        remaining = normalize_line(spec_text.lstrip("〃").strip())
        if not previous_spec:
            return remaining
        if not remaining:
            return previous_spec
        previous_parts = previous_spec.split()
        base_parts = previous_parts[:-1] if len(previous_parts) > 1 else []
        return " ".join(base_parts + remaining.split())

    return spec_text


def parse_single_price_lines(
    report_month: str,
    source_file: str,
    section_key: str,
    section_name: str,
    section_order: int,
    lines: Iterable[str],
) -> list[PriceRecord]:
    records: list[PriceRecord] = []
    for line in lines:
        if not SPEC_RE.search(line):
            continue
        for segment in split_segments_by_spec(line):
            parsed = parse_single_price_segment(segment)
            if not parsed:
                continue
            spec, unit, price, detail = parsed
            records.append(
                PriceRecord(
                    report_month=report_month,
                    source_file=source_file,
                    section_key=section_key,
                    section_name=section_name,
                    section_order=section_order,
                    spec=spec,
                    spec_value=spec_to_float(spec),
                    variant="",
                    variant_order=0,
                    unit=unit,
                    price=price,
                    detail=detail,
                )
            )
    return deduplicate_records(records)


def parse_fw_cv_lines(
    report_month: str,
    source_file: str,
    section_name: str,
    section_order: int,
    lines: Iterable[str],
) -> list[PriceRecord]:
    records: list[PriceRecord] = []

    for line in lines:
        if not line or not SPEC_RE.match(line):
            continue

        tokens = line.split()
        spec = tokens[0]
        unit_index = find_unit_index(tokens)
        if unit_index is None:
            continue

        unit = tokens[unit_index]
        detail = " ".join(tokens[1:unit_index]).strip()
        values = [token for token in tokens[unit_index + 1 :] if is_value_token(token)]
        if len(values) < len(FW_CV_VARIANTS):
            continue

        for variant, value_token in zip(FW_CV_VARIANTS, values[: len(FW_CV_VARIANTS)]):
            if value_token == "-":
                continue
            records.append(
                PriceRecord(
                    report_month=report_month,
                    source_file=source_file,
                    section_key="fw_cv",
                    section_name=section_name,
                    section_order=section_order,
                    spec=spec,
                    spec_value=spec_to_float(spec),
                    variant=variant,
                    variant_order=VARIANT_ORDER[variant],
                    unit=unit,
                    price=parse_price(value_token),
                    detail=detail,
                )
            )

    return deduplicate_records(records)


def parse_al_tfr_cv_lines(
    report_month: str,
    source_file: str,
    section_name: str,
    section_order: int,
    lines: Iterable[str],
) -> list[PriceRecord]:
    records: list[PriceRecord] = []

    for line in lines:
        if not SPEC_RE.search(line):
            continue

        for segment in split_segments_by_spec(line):
            tokens = segment.split()
            if not tokens or not SPEC_RE.fullmatch(tokens[0]):
                continue

            unit_index = find_unit_index(tokens)
            if unit_index is None:
                continue

            spec = tokens[0]
            unit = tokens[unit_index]
            detail = " ".join(tokens[1:unit_index]).strip()
            values = [token for token in tokens[unit_index + 1 :] if is_value_token(token)]
            if len(values) < len(AL_TFR_VARIANTS):
                continue

            for variant, value_token in zip(AL_TFR_VARIANTS, values[: len(AL_TFR_VARIANTS)]):
                if value_token == "-":
                    continue
                records.append(
                    PriceRecord(
                        report_month=report_month,
                        source_file=source_file,
                        section_key="al_tfr_cv",
                        section_name=section_name,
                        section_order=section_order,
                        spec=spec,
                        spec_value=spec_to_float(spec),
                        variant=variant,
                        variant_order=VARIANT_ORDER[variant],
                        unit=unit,
                        price=parse_price(value_token),
                        detail=detail,
                    )
                )

    return deduplicate_records(records)


def split_segments_by_spec(line: str) -> list[str]:
    matches = list(SPEC_RE.finditer(line))
    segments: list[str] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        segment = line[start:end].strip()
        if segment:
            segments.append(segment)

    return segments


def parse_single_price_segment(segment: str) -> tuple[str, str, float, str] | None:
    tokens = segment.split()
    if not tokens or not SPEC_RE.fullmatch(tokens[0]):
        return None

    price_index = None
    for index in range(len(tokens) - 1, 0, -1):
        if is_number_token(tokens[index]):
            price_index = index
            break
    if price_index is None:
        return None

    unit_index = None
    for index in range(price_index - 1, 0, -1):
        if tokens[index] in {"m", "〃"}:
            unit_index = index
            break

    spec = tokens[0]
    unit = tokens[unit_index] if unit_index is not None else ""
    detail_end = unit_index if unit_index is not None else price_index
    detail = " ".join(tokens[1:detail_end]).strip()
    return spec, unit, parse_price(tokens[price_index]), detail


def find_unit_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens[1:], start=1):
        if token in {"m", "〃"}:
            return index
    return None


def parse_price(token: str) -> float:
    return float(token.replace(",", ""))


def spec_to_float(spec: str) -> float:
    return float(spec.upper().replace("SQ", ""))


def is_value_token(token: str) -> bool:
    return bool(VALUE_TOKEN_RE.fullmatch(token))


def is_number_token(token: str) -> bool:
    return token != "-" and is_value_token(token)


def deduplicate_records(records: list[PriceRecord]) -> list[PriceRecord]:
    seen: dict[tuple[str, str], PriceRecord] = {}
    for record in records:
        key = (record.item_code, record.report_month)
        seen[key] = record
    return list(seen.values())
