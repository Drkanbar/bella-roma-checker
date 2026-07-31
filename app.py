import io
import os
import re
import hashlib
import streamlit as st
from PIL import Image, ImageOps
import fitz  # PyMuPDF
import pytesseract
from pytesseract import TesseractNotFoundError

# iPhone photos are HEIC by default; register the opener if the lib is installed.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:
    HEIF_SUPPORTED = False

#
# Config
#
st.set_page_config(
    page_title="Bella Roma Checker",
    layout="centered",
    page_icon="🩺",
    initial_sidebar_state="collapsed",
)

BUILD = "2026-07-31-c"

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif")
PDF_EXT = (".pdf",)
MAX_OCR_PAGES = 20
LARGE_FILE_MB = 12
OCR_DPI = 200

# ---------------------------------------------------------------------------
# Required tests
#
# CBC and PT/INR are broken out into their real individual parameters rather
# than one lumped "CBC / Hemoglobin" or "PT / INR" bucket. The old lumped
# entries could only ever capture ONE value for the whole panel, so if the
# keyword search happened to land on (say) Hemoglobin, an abnormal Hematocrit,
# RDW, or differential count elsewhere in the same panel was silently never
# looked at. Each parameter now gets its own check, so nothing in the panel
# can hide behind another.
# ---------------------------------------------------------------------------
CBC_TESTS = {
    "Hemoglobin":     {"strong": ["HEMOGLOBIN", "HAEMOGLOBIN"], "min": 12.0, "max": 16.5, "validate": "not_glycated"},
    "Hematocrit":     {"strong": ["HEMATOCRIT", "HAEMATOCRIT"], "min": 36.0, "max": 46.0},
    "RBC Count":      {"strong": ["RBC COUNT", "RBC"], "min": 4.0, "max": 5.5},
    "WBC Count":      {"strong": ["WBC COUNT", "WBC"], "min": 4.0, "max": 11.0},
    "Platelet Count": {"strong": ["PLATELET COUNT", "PLATELET", "PLATELETS"], "min": 150.0, "max": 400.0},
    "MCV":            {"strong": ["MCV"], "min": 80.0, "max": 100.0},
    "MCH":            {"strong": ["MCH"], "min": 27.0, "max": 33.0},
    "RDW":            {"strong": ["RDW"], "min": 11.5, "max": 14.5, "validate": "not_rdw_sd"},
    "Neutrophils %":  {"strong": ["NEUTROPHIL"], "min": 40.0, "max": 75.0},
    "Lymphocytes %":  {"strong": ["LYMPHOCYTE"], "min": 20.0, "max": 45.0},
    "Eosinophils %":  {"strong": ["EOSINOPHIL"], "min": 1.0, "max": 6.0},
    "Monocytes %":    {"strong": ["MONOCYTE"], "min": 2.0, "max": 10.0},
    "Basophils %":    {"strong": ["BASOPHIL"], "min": 0.0, "max": 2.0},
}

BASE_TESTS = {}
BASE_TESTS.update(CBC_TESTS)
BASE_TESTS.update({
    "Ferritin": {"strong": ["FERRITIN"], "min": 13.0, "max": 150.0},
    "Iron": {"strong": ["IRON", "SERUM IRON", "TIBC", "TRANSFERRIN"], "min": 60.0, "max": 170.0},
    "SGPT / ALT": {
        "strong": ["SGPT", "ALANINE AMINOTRANSFERASE", "ALANINE TRANSAMINASE"],
        "weak": ["ALT"],
        "min": 7.0, "max": 56.0
    },
    "SGOT / AST": {
        "strong": ["SGOT", "ASPARTATE AMINOTRANSFERASE", "ASPARTATE TRANSAMINASE"],
        "weak": ["AST"],
        "min": 10.0, "max": 40.0
    },
    "Urea": {"strong": ["UREA", "BLOOD UREA", "BUN"], "min": 15.0, "max": 45.0},
    "Creatinine": {"strong": ["CREATININE", "CREATENINE"], "min": 0.6, "max": 1.2},
    "Prothrombin Time (PT)": {
        "strong": ["PROTHROMBIN TIME", "PROTHROMBIN"],
        "weak": ["PT"],
        "min": 9.0, "max": 13.0
    },
    "INR": {
        "strong": ["INTERNATIONAL NORMALIZED RATIO", "INR"],
        "min": 0.8, "max": 1.2
    },
    "APTT": {
        "strong": [
            "APTT",
            "PTT",
            "ACTIVATED PARTIAL THROMBOPLASTIN",
            "ACTIVATED PARTIAL",
        ],
        "min": 30.0, "max": 40.0
    },
    "Blood Group (ABO & Rh)": {
        "strong": [
            "BLOOD GROUP",
            "BLOOD GROUPING",
            "RH TYPE",
            "RH FACTOR",
            "RH D",
            "RHESUS",
            "ABO GROUP",
            "ABO AND RH",
            "GROUPING AND RH",
        ],
        "weak": ["ABO"],
    },
    "HbA1c": {
        "strong": [
            "HBA1C",
            "HB A1C",
            "GLYCOSYLATED HEMOGLOBIN",
            "GLYCATED HEMOGLOBIN",
            "GLYCATED HAEMOGLOBIN",
        ],
        "min": 4.0, "max": 5.6
    },
    "RBS / Glucose": {
        "strong": [
            "GLUCOSE",
            "RBS",
            "FBS",
            "RANDOM BLOOD SUGAR",
            "FASTING BLOOD SUGAR",
            "BLOOD SUGAR",
        ],
        "min": 70.0, "max": 100.0
    },
    "TSH": {"strong": ["THYROID STIMULATING HORMONE", "TSH"], "min": 0.4, "max": 4.0},
    "T3": {"strong": ["FREE T3", "FT3", "TRIIODOTHYRONINE"], "weak": ["T3"], "min": 2.0, "max": 4.4},
    "T4": {"strong": ["FREE T4", "FT4", "THYROXINE"], "weak": ["T4"], "min": 0.9, "max": 1.7},
    "HIV": {"strong": ["HIV", "HUMAN IMMUNODEFICIENCY"]},
    "HBsAg": {
        "strong": ["HBSAG", "HBS AG", "HEPATITIS B SURFACE", "HEPATITIS B"]
    },
    "Hepatitis C (HCV)": {"strong": ["HEPATITIS C", "HCV", "ANTI HCV"]},
    "CRP": {"strong": ["CRP", "C REACTIVE PROTEIN"], "min": 0.0, "max": 5.0},
    "Sodium": {"strong": ["SODIUM", "NATRIUM"], "weak": ["NA+"], "min": 135.0, "max": 145.0},
    "Potassium": {"strong": ["POTASSIUM", "KALIUM"], "weak": ["K+"], "min": 3.5, "max": 5.1},
    "Calcium": {"strong": ["CALCIUM"], "min": 8.5, "max": 10.5},
    "Magnesium": {"strong": ["MAGNESIUM"], "min": 1.7, "max": 2.2},
})

PREGNANCY_TEST = {
    "Beta HCG (Pregnancy Test)": {
        "strong": [
            "BETA HCG",
            "B HCG",
            "HCG",
            "PREGNANCY TEST",
            "PREGNANCY",
        ],
        "min": 0.0, "max": 5.0
    }
}

AGE_TESTS = {
    "Chest X-ray": {
        "strong": [
            "CHEST X RAY",
            "CHEST XRAY",
            "CXR",
            "CHEST RADIOGRAPH",
            "CHEST PA",
            "CHEST PA VIEW",
        ]
    },
    "ECG": {
        "strong": [
            "ECG",
            "EKG",
            "ELECTROCARDIOGRAM",
            "ELECTROCARDIOGRAPHY",
        ]
    },
}

FIELD_WORDS = r"\b(NAME|ID|NO|NUMBER|AGE|SEX|GENDER|DOB|ADDRESS|PHONE|MOBILE|REF|REFERENCE|DOCTOR|DR|CLINIC|BARCODE|SAMPLE|VISIT|FILE)\b"
NUM_RE = re.compile(r'\b\d+\.?\d*\b')
FLAG_TOKENS = {"H", "HH", "L", "LL"}

#
# Text normalisation & matching
#
def normalize(text: str) -> str:
    """Uppercase and tidy punctuation, but KEEP line breaks intact.

    The matcher below relies on line structure to localize each test's value
    to its own row. Collapsing all whitespace (including newlines) into single
    spaces -- which a plain ``re.sub(r"\\s+", " ", t)`` does -- merges an
    entire multi-page report into one giant line, and every test then "sees"
    the whole document as its search window instead of just its own row.
    """
    t = text.upper().replace("\u00a0", " ")
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", t)
    t = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", "", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)      # collapse horizontal whitespace only
    t = re.sub(r" *\n *", "\n", t)     # trim spaces around line breaks
    t = re.sub(r"\n{2,}", "\n", t)     # drop blank lines
    return t.strip()

def keyword_pattern(keyword: str) -> str:
    parts = [re.escape(p) for p in re.split(r"[\s\-.]+", keyword.strip()) if p]
    core = r"[\s\-.]*".join(parts)
    return r"(?<![A-Z0-9])" + core + r"(?![A-Z0-9])"

def weak_hit_is_real(lines, idx, match) -> bool:
    line = lines[idx]
    tail = line[match.end(): match.end() + 80]
    if re.match(r"\s*[:.\-]?\s*" + FIELD_WORDS + r"(?![A-Z])", tail):
        return False
    return bool(NUM_RE.search(tail))

def not_glycated(lines, idx, match) -> bool:
    """Reject a 'Hemoglobin'/'Haemoglobin' hit that's actually part of
    'Glycated Hemoglobin' (HbA1c) -- a different, already separately-handled
    test whose row otherwise looks just as valid (number + range) as the
    real CBC Hemoglobin row, so it can win purely by appearing earlier."""
    head = lines[idx][:match.start()]
    return not re.search(r"(GLYCATED|GLYCOSYLATED)\s*$", head)

def not_rdw_sd(lines, idx, match) -> bool:
    """Reject 'RDW' when it's actually the start of 'RDW-SD', a separate
    CBC parameter with its own row and reference range."""
    tail = lines[idx][match.end(): match.end() + 4]
    return not tail.startswith("-SD")

VALIDATORS = {"not_glycated": not_glycated, "not_rdw_sd": not_rdw_sd}

PROSE_HINTS = re.compile(
    r"\b(MAY|CAN|SHOULD|MUST|CAUSE[SD]?|FALSELY|ELEVATE[SD]?|LOWERED|INCREASE[SD]?|"
    r"DECREASE[SD]?|PATIENTS?|RECOMMEND\w*|CRITERI\w+|DIAGNOS\w+|INTERPRET\w*|"
    r"IMPLICATION\w*|INTERFERING|FACTORS?|COMMENTS?|REMARKS?|THERAPY|TREATMENT|"
    r"ASSOCIATED|SUGGEST\w*|INDICAT\w+|CLINICAL|USEFUL|MONITOR\w*|ADVIS\w+|"
    r"CORRELAT\w+|CONSIDER\w*|EXERCISE|INTAKE|PLEASE|KINDLY|REPEAT\w*|"
    r"FOLLOW UP|DUE TO|SUCH AS|IN CASE)\b"
)

def _looks_like_prose(line: str) -> bool:
    """Reject clinical-notes / interpretation sentences so they can never be
    mistaken for a result row.

    Lab reports carry a lot of explanatory prose that happens to name other
    tests -- e.g. the Glucose test's own ADA criteria paragraph mentions
    "HbA1c > 6.5%", and its interfering-factors note mentions
    "Hematocrit > 55%". Those sentences contain numbers, so a purely
    numeric heuristic can score them as plausible result rows. Structure is
    what separates them: real rows are short, start with the test name, and
    carry a unit and a reference range; prose is long, often bulleted, and
    reads as a sentence.
    """
    if re.match(r"^\s*[\(\[]?\d+\s*[\)\.\]]\s+\S", line):   # "2) ..." / "3. ..." bullets
        return True
    if len(line) > 90:
        return True
    if PROSE_HINTS.search(line):
        return True
    if line.rstrip().endswith(".") and len(line.split()) > 6:
        return True
    # Interpretation-guide labels, e.g. "IRON OVERLOAD : > 200",
    # "DEFICIENCY : < 10" -- a cutoff legend, not a measured result.
    if re.match(r"^[A-Z][A-Z \-/()]{2,40}\s*:\s*[<>]", line):
        return True
    return False

def _has_range(line: str) -> bool:
    return bool(
        re.search(r'\d+\.?\d*\s*[\-\u2013\u2014\~]+\s*\d+\.?\d*', line)
        or re.search(r'[<\u2264]\s*\d+\.?\d*', line)
    )

def _line_has_number(lines, idx):
    return 0 <= idx < len(lines) and bool(NUM_RE.search(lines[idx]))

def _best_occurrence(lines, kw, numeric_test, validate=None):
    """Scan every line mentioning kw, score each occurrence, return the best.

    Scoring is deliberately layout-independent, because different PDF text
    engines emit the same table row differently: some join a row into one
    line ("GLUCOSE (RANDOM) 83 MG/DL 70 - 140"), others put each cell on its
    own line. Both shapes have to work, so a name-only line followed by the
    value block scores nearly as well as a self-contained row -- and prose is
    rejected outright rather than being allowed to outrank either.

    0  self-contained result row: number and reference range on the line
    1  name on its own line, with a number and a range just below
    2  number on the line, no range
    3  name on its own line with a number below, no range
    7  keyword present but nothing numeric nearby (bare panel heading)
    8  prose / clinical-notes sentence -- last resort only
    Ties go to the earliest occurrence in the document.
    """
    pat = keyword_pattern(kw)
    best = None  # (score, idx)
    for idx, line in enumerate(lines):
        m = re.search(pat, line)
        if not m:
            continue
        if validate and not validate(lines, idx, m):
            continue
        if not numeric_test:
            if _looks_like_prose(line) and best is not None:
                continue
            if not _looks_like_prose(line):
                return idx
            score = 8
        elif _looks_like_prose(line):
            score = 8
        elif _line_has_number(lines, idx):
            score = 0 if _has_range(line) else 2
        else:
            # Investigation name on its own line -- either a wrapped name
            # (e.g. APTT) or a cell-per-line table layout. Look ahead for the
            # value block.
            ahead = [lines[idx + o] for o in (1, 2, 3) if idx + o < len(lines)]
            if any(NUM_RE.search(a) for a in ahead):
                score = 1 if _has_range(" ".join(ahead)) else 3
            else:
                score = 7
        at_start = m.start() <= 2
        rank = (score, 0 if at_start else 1)
        if best is None or rank < best[0]:
            best = (rank, idx)
            if rank == (0, 0):
                break
    return best[1] if best else None

def find_test_with_value(text: str, spec: dict):
    lines = text.split("\n")
    numeric_test = spec.get("min") is not None or spec.get("max") is not None
    validate = VALIDATORS.get(spec.get("validate"))

    matched_kw, matched_line_idx = None, None
    for kw in spec.get("strong", []):
        idx = _best_occurrence(lines, kw, numeric_test, validate=validate)
        if idx is not None:
            matched_kw, matched_line_idx = kw, idx
            break
    if matched_kw is None:
        for kw in spec.get("weak", []):
            def wv(ls, i, m, _validate=validate):
                return weak_hit_is_real(ls, i, m) and (not _validate or _validate(ls, i, m))
            idx = _best_occurrence(lines, kw, numeric_test, validate=wv)
            if idx is not None:
                matched_kw, matched_line_idx = kw, idx
                break

    if matched_kw is None or matched_line_idx is None:
        return None

    val_info = {
        "keyword": matched_kw,
        "value": None,
        "status": "FOUND",
        "min": spec.get("min"),
        "max": spec.get("max"),
        "range_source": "Default"
    }

    # Locate the actual data row: the matched line itself if it carries a
    # number, otherwise scan forward up to 2 lines (handles investigation
    # names that wrap before the value appears, e.g. APTT).
    value_line_idx = matched_line_idx
    if not _line_has_number(lines, value_line_idx):
        for offset in (1, 2, 3):
            if _line_has_number(lines, matched_line_idx + offset):
                value_line_idx = matched_line_idx + offset
                break

    value_line = lines[value_line_idx] if 0 <= value_line_idx < len(lines) else ""
    # Under a cell-per-line layout the unit and reference range land on the
    # lines after the value, so the fallback window reaches a little further.
    next_line = " ".join(
        lines[value_line_idx + o]
        for o in (1, 2, 3)
        if value_line_idx + o < len(lines)
    )

    def ranges_in(s):
        rm = re.search(r'(\d+\.?\d*)\s*[\-\–\—\~]+\s*(\d+\.?\d*)', s)
        lm = re.search(r'[<≤]\s*(\d+\.?\d*)', s)
        return rm, lm

    # Look for the reference range on the value's own line first; only pull
    # in the next line if nothing usable is on the value line itself. This
    # keeps a neighbouring row's numbers (e.g. T4 leaking into T3) out of the
    # picture whenever the value line already has everything it needs.
    for search_text in (value_line, value_line + " " + next_line):
        rm, lm = ranges_in(search_text)
        if rm or lm:
            if rm and lm:
                # Whichever pattern starts earlier (closer to the value) wins.
                # This is what keeps e.g. HbA1c's "<5.7 non-diabetic
                # 5.7-6.4 pre-diabetic" tier label from being mistaken for the
                # actual normal reference band.
                use_range = rm.start() <= lm.start()
            else:
                use_range = bool(rm)
            if use_range:
                rmin, rmax = float(rm.group(1)), float(rm.group(2))
                if rmin <= rmax:
                    val_info["min"], val_info["max"], val_info["range_source"] = rmin, rmax, "Report"
                    break
            else:
                val_info["min"], val_info["max"], val_info["range_source"] = 0.0, float(lm.group(1)), "Report"
                break

    # Extract the value strictly from the value line itself (not a blended
    # multi-line window) so a neighbouring test's numbers can't leak in.
    matches = list(NUM_RE.finditer(value_line))
    chosen = None
    for m in matches:
        num = float(m.group())
        if num >= 10000 and num.is_integer():
            continue
        if val_info["min"] is not None and num == val_info["min"]:
            continue
        if val_info["max"] is not None and num == val_info["max"]:
            continue
        chosen = m
        break
    if chosen is None and matches:
        chosen = matches[0]

    if chosen is not None:
        val = float(chosen.group())
        val_info["value"] = val

        # Flag = the token immediately following the value (e.g. "9.4 L g/dl"
        # -> "L"), not any standalone L/H found anywhere in the surrounding
        # text. Scanning the whole window for a bare "L" previously matched
        # the "L" in units like mmol/L, µg/L, and U/L, which produced a false
        # LOW on otherwise-normal results (ALT, AST, Sodium, Potassium,
        # Ferritin, CRP all use such units).
        tail = value_line[chosen.end():]
        tok_m = re.match(r'\s*([A-Z]{1,2})\b', tail)
        flag = tok_m.group(1) if tok_m and tok_m.group(1) in FLAG_TOKENS else None

        ref_min, ref_max = val_info["min"], val_info["max"]
        if flag in ("L", "LL"):
            val_info["status"] = "LOW"
        elif flag in ("H", "HH"):
            val_info["status"] = "HIGH"
        elif ref_min is not None and val < ref_min:
            val_info["status"] = "LOW"
        elif ref_max is not None and val > ref_max:
            val_info["status"] = "HIGH"
        elif ref_min is not None or ref_max is not None:
            val_info["status"] = "NORMAL"
        # else: no range and no flag at all -> leave as "FOUND" (a purely
        # qualitative test such as HIV / HBsAg / HCV / Blood Group)

    return val_info

def build_required_tests(age: int, gender: str) -> dict:
    tests = dict(BASE_TESTS)
    if gender == "Female" and age < 80:
        tests.update(PREGNANCY_TEST)
    if age >= 40:
        tests.update(AGE_TESTS)
    return tests

#
# OCR / extraction
#
def prepare_for_ocr(img: Image.Image) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    img = ImageOps.grayscale(img)
    w, h = img.size
    long_side = max(w, h)
    if long_side < 1600:
        scale = 1600 / long_side
    elif long_side > 3000:
        scale = 3000 / long_side
    else:
        scale = 1.0
    if scale != 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(img)

def ocr_image(img: Image.Image) -> str:
    img = prepare_for_ocr(img)
    text = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
    if len(text.strip()) < 80:
        alt = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 3")
        if len(alt.strip()) > len(text.strip()):
            text = alt
    return text

def read_pdf(data: bytes):
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages = doc.page_count
        native = []
        for i in range(pages):
            native.append(doc.load_page(i).get_text("text") or "")
        native_text = "\n".join(native)
        if len(native_text.strip()) >= 40:
            return native_text, f"PDF text ({pages} page(s))"
        ocr_parts = []
        for i in range(min(pages, MAX_OCR_PAGES)):
            pix = doc.load_page(i).get_pixmap(dpi=OCR_DPI, colorspace=fitz.csGRAY)
            ocr_parts.append(ocr_image(Image.open(io.BytesIO(pix.tobytes("png")))))
        note = f"Scanned PDF OCR on {min(pages, MAX_OCR_PAGES)}/{pages} page(s)"
        return native_text + "\n" + "\n".join(ocr_parts), note
    finally:
        doc.close()

@st.cache_data(show_spinner=False, max_entries=80)
def extract_text(data: bytes, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext in PDF_EXT:
            text, note = read_pdf(data)
        elif ext in IMAGE_EXT:
            if ext in (".heic", ".heif") and not HEIF_SUPPORTED:
                return "", "HEIC not supported on this server", False
            text = ocr_image(Image.open(io.BytesIO(data)))
            note = "Image OCR"
        else:
            if data[:5] == b"%PDF-":
                text, note = read_pdf(data)
            else:
                try:
                    text = ocr_image(Image.open(io.BytesIO(data)))
                    note = "Image OCR"
                except Exception:
                    return "", f"Unsupported file type", False
        return text, note, True
    except TesseractNotFoundError:
        raise
    except Exception as exc:
        return "", f"Could not read this file: {exc}", False

#
# UI
#
st.title("Pre-Surgery Lab Tests Checker")
st.caption("Upload the patient's reports as PDFs or photos one at a time or all at once.")
st.caption(f"Matching engine build: {BUILD}")

if "documents" not in st.session_state:
    st.session_state.documents = {}

st.subheader("1. Patient information")
c1, c2, c3 = st.columns(3)
with c1:
    patient_name = st.text_input("Patient name", "")
with c2:
    patient_age = st.number_input("Age", min_value=1, max_value=120, value=25)
with c3:
    patient_gender = st.selectbox("Gender", ["Female", "Male"])

st.divider()
st.subheader("2. Medical reports")

with st.form("upload_form", clear_on_submit=False):
    uploaded_files = st.file_uploader(
        "Select PDFs or photos",
        accept_multiple_files=True,
        help="PDF, JPG, PNG, WEBP, TIFF and HEIC all work. Select several at once.",
        key="uploader"
    )
    pasted_text = st.text_area(
        "Or paste the report text here (fallback if your browser blocks uploads)",
        height=100,
        placeholder="Hemoglobin 12.4 g/dL 12.0 - 16.5\nPlatelets 250 10^3/uL 150 - 400\n(one result per line works best)"
    )
    analyze = st.form_submit_button("Analyze reports", type="primary", use_container_width=True)

if analyze:
    files = uploaded_files or []
    if not files and not pasted_text.strip():
        st.warning("Add at least one file or paste some report text, then press Analyze.")
    else:
        st.session_state.documents = {}
        progress = st.progress(0.0, text="Reading files...")
        total = max(1, len(files))
        try:
            for i, f in enumerate(files):
                raw = f.getvalue()
                digest = hashlib.md5(raw).hexdigest()
                progress.progress(i / total, text=f"Reading {f.name} ({i + 1}/{total})")
                if digest in st.session_state.documents:
                    continue
                size_mb = len(raw) / (1024 * 1024)
                text, note, ok = extract_text(raw, f.name)
                if size_mb > LARGE_FILE_MB:
                    note += f" ({size_mb:.0f} MB)"
                st.session_state.documents[digest] = {
                    "name": f.name, "text": text, "note": note, "ok": ok
                }
            if pasted_text.strip():
                st.session_state.documents["pasted"] = {
                    "name": "Pasted text", "text": pasted_text, "note": "Typed by hand", "ok": True
                }
            progress.progress(1.0, text="Done")
        except TesseractNotFoundError:
            progress.empty()
            st.error("Tesseract OCR is not installed on the server. Add a packages.txt containing tesseract-ocr and tesseract-ocr-eng, then redeploy.")

docs = st.session_state.documents
if docs:
    st.divider()
    st.subheader("3. Files read")
    for d in docs.values():
        chars = len(d["text"].strip())
        if d["ok"] and chars > 0:
            st.write(f"• **{d['name']}** — {d['note']} ({chars:,} characters)")
        elif d["ok"]:
            st.write(f"⚠️ **{d['name']}** — no readable text found. Retake the photo in better light, straight on, filling the frame.")
        else:
            st.write(f"❌ **{d['name']}** — {d['note']}")

    combined = normalize("\n".join(d["text"] for d in docs.values()))
    if combined.strip():
        required = build_required_tests(int(patient_age), patient_gender)

        found, abnormal, missing = {}, {}, []

        for name, spec in required.items():
            res = find_test_with_value(combined, spec)
            if res:
                if res["status"] in ["HIGH", "LOW"]:
                    abnormal[name] = res
                else:
                    found[name] = res
            else:
                missing.append(name)

        st.divider()
        st.subheader("4. Audit result")
        done = len(found) + len(abnormal)
        st.progress(done / len(required), text=f"{done} of {len(required)} required tests found")

        col_normal, col_abnormal, col_missing = st.columns(3)

        with col_normal:
            st.success(f"Normal ({len(found)})")
            for name, data in found.items():
                val_str = f" : {data['value']}" if data['value'] is not None else ""
                st.write(f"• **{name}**{val_str}\n <span style='color:#888;font-size:0.8em'>({data['keyword']})</span>", unsafe_allow_html=True)

        with col_abnormal:
            if abnormal:
                st.warning(f"Out of Range ({len(abnormal)})")
                for name, data in abnormal.items():
                    tag = "🔺 HIGH" if data["status"] == "HIGH" else "🔻 LOW"
                    src_tag = "من التقرير" if data["range_source"] == "Report" else "افتراضي"
                    range_info = f"Ref: {data['min']} - {data['max']} ({src_tag})" if data['min'] is not None else ""
                    st.write(f"• **{name}**: {data['value']} ➡️ **{tag}**\n <span style='color:#888;font-size:0.8em'>({range_info})</span>", unsafe_allow_html=True)
            else:
                st.success("No abnormal values")

        with col_missing:
            if missing:
                st.error(f"Missing ({len(missing)})")
                for name in missing:
                    st.write(f"• **{name}**")
            else:
                st.success("Nothing missing")

        st.divider()
        if missing or abnormal:
            st.warning(f"⚠️ Action needed: {len(missing)} missing test(s), {len(abnormal)} out-of-range value(s).")
        else:
            st.success("✅ The file is complete — all required tests are present and within normal limits.")

        summary = [
            "Pre-Surgery Lab Tests Checker",
            f"Patient: {patient_name or '-'} | Age: {int(patient_age)} | Gender: {patient_gender}",
            f"Files: {', '.join(d['name'] for d in docs.values())}",
            "",
            f"NORMAL ({len(found)}):",
            *[f"• {n}: {d['value'] if d['value'] is not None else 'Present'}" for n, d in found.items()],
            "",
            f"OUT OF RANGE ({len(abnormal)}):",
            *[f"• {n}: {d['value']} ({d['status']}) [Range Source: {d['range_source']}]" for n, d in abnormal.items()],
            "",
            f"MISSING ({len(missing)}):",
            *[f"• {n}" for n in missing],
        ]
        st.download_button(
            "Download summary",
            "\n".join(summary),
            file_name=f"lab_check_{(patient_name or 'patient').replace(' ', '_')}.txt",
            use_container_width=True,
        )

        with st.expander("View the raw extracted text"):
            for d in docs.values():
                st.markdown(f"**{d['name']}**")
                st.text(d["text"][:20000] or "(empty)")
else:
    st.warning("No readable text came out of these files. If they are photos, retake straight on in good light with the text filling the frame, or paste text into the box above.")
