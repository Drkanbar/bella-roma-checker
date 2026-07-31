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

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif")
PDF_EXT = (".pdf",)
MAX_OCR_PAGES = 20
LARGE_FILE_MB = 12
OCR_DPI = 200

# Base tests with Default Fallback Ranges (used only if not printed in the lab report)
BASE_TESTS = {
    "CBC / Hemoglobin": {
        "strong": [
            "CBC",
            "COMPLETE BLOOD COUNT",
            "HEMOGLOBIN",
            "HAEMOGLOBIN",
            "PLATELET",
            "PLATELETS",
            "WBC",
            "RBC",
            "HEMATOCRIT",
            "HAEMATOCRIT",
        ],
        "min": 12.0, "max": 16.5
    },
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
    "PT / INR": {
        "strong": ["PROTHROMBIN TIME", "PROTHROMBIN", "INR"],
        "weak": ["PT"],
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
    "TSH": {"strong": ["TSH", "THYROID STIMULATING HORMONE"], "min": 0.4, "max": 4.0},
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
}

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

#
# Text normalisation & matching
#
def normalize(text: str) -> str:
    t = text.upper().replace("\u00a0", " ")
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", t)
    t = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def keyword_pattern(keyword: str) -> str:
    parts = [re.escape(p) for p in re.split(r"[\s\-.]+", keyword.strip()) if p]
    core = r"[\s\-.]*".join(parts)
    return r"(?<![A-Z0-9])" + core + r"(?![A-Z0-9])"

def weak_hit_is_real(text: str, match) -> bool:
    tail = text[match.end(): match.end() + 80]
    if re.match(r"\s*[:.\-]?\s*" + FIELD_WORDS + r"(?![A-Z])", tail):
        return False
    return bool(re.search(r"\d", tail))

def find_test_with_value(text: str, spec: dict, patient_age: int):
    matched_kw = None
    lines = text.split("\n")
    matched_line_idx = -1
    
    # 1. Check strong keywords
    for kw in spec.get("strong", []):
        pat = keyword_pattern(kw)
        for idx, line in enumerate(lines):
            if re.search(pat, line):
                matched_kw = kw
                matched_line_idx = idx
                break
        if matched_kw:
            break
            
    # 2. Check weak keywords if no strong hit
    if not matched_kw:
        for kw in spec.get("weak", []):
            pat = keyword_pattern(kw)
            for idx, line in enumerate(lines):
                if re.search(pat, line) and weak_hit_is_real(text, re.search(pat, line)):
                    matched_kw = kw
                    matched_line_idx = idx
                    break
            if matched_kw:
                break

    if not matched_kw or matched_line_idx == -1:
        return None

    val_info = {
        "keyword": matched_kw,
        "value": None,
        "status": "FOUND",
        "min": spec.get("min"),
        "max": spec.get("max"),
        "range_source": "Default"
    }
    
    line_text = lines[matched_line_idx]
    next_line = lines[matched_line_idx + 1] if matched_line_idx + 1 < len(lines) else ""
    window_text = line_text + " " + next_line
    window_text = re.sub(r'\s+', ' ', window_text)

    # 3. Search for range pattern in the window
    range_match = re.search(r'(\d+\.?\d*)\s*[\-\–\—\~|to]+\s*(\d+\.?\d*)', window_text)
    less_than_match = re.search(r'<\s*(\d+\.?\d*)', window_text)
    
    if range_match:
        rmin = float(range_match.group(1))
        rmax = float(range_match.group(2))
        if rmin <= rmax:
            val_info["min"] = rmin
            val_info["max"] = rmax
            val_info["range_source"] = "Report"
    elif less_than_match:
        val_info["min"] = 0.0
        val_info["max"] = float(less_than_match.group(1))
        val_info["range_source"] = "Report"

    # 4. Clean window text by removing dates, years, and time patterns (e.g., 17:00, 30/07, 2026)
    window_text_clean = re.sub(r'\b\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?\b', ' ', window_text)
    window_text_clean = re.sub(r'\b20\d{2}\b', ' ', window_text_clean)
    window_text_clean = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\b', ' ', window_text_clean, flags=re.IGNORECASE)
    window_text_clean = re.sub(r'\b\d{1,2}\s*(?:HRS|HOURS|AM|PM)\b', ' ', window_text_clean, flags=re.IGNORECASE)

    # 5. Extract numbers from the cleaned window text and filter out IDs, barcodes, and patient age
    numbers = re.findall(r'\b\d+\.?\d*\b', window_text_clean)
    
    if numbers:
        candidate_vals = []
        for n_str in numbers:
            num = float(n_str)
            # Skip ID-like large integers or if it matches patient age
            if (num >= 10000 and num.is_integer()) or num == float(patient_age):
                continue
            # Skip if it matches range bounds
            if val_info["min"] is not None and num == val_info["min"]:
                continue
            if val_info["max"] is not None and num == val_info["max"]:
                continue
            candidate_vals.append(num)
            
        if candidate_vals:
            val_info["value"] = candidate_vals[0]
        else:
            for n_str in numbers:
                num = float(n_str)
                if not ((num >= 10000 and num.is_integer()) or num == float(patient_age)):
                    val_info["value"] = num
                    break
            if val_info["value"] is None and numbers:
                val_info["value"] = float(numbers[0])
            
        val = val_info["value"]
        ref_min = val_info["min"]
        ref_max = val_info["max"]
        
        # 6. Numerical comparison & flags check
        if val is not None:
            if ref_min is not None and val < ref_min:
                val_info["status"] = "LOW"
            elif ref_max is not None and val > ref_max:
                val_info["status"] = "HIGH"
            else:
                has_high_flag = bool(re.search(r'\b(HIGH|HI|H)\b|\([HH]\)|\[[HH]\]|\*[HH]\*', window_text))
                has_low_flag = bool(re.search(r'\b(LOW|LO|L)\b|\([LL]\)|\[[LL]\]|\*[LL]\*', window_text))
                
                if has_high_flag and not has_low_flag:
                    val_info["status"] = "HIGH"
                elif has_low_flag and not has_high_flag:
                    val_info["status"] = "LOW"
                else:
                    val_info["status"] = "NORMAL"

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

if "documents" not in st.session_state:
    st.session_state.documents = {}

st.subheader("1. Patient information")
c1, c2, c3 = st.columns(3)
with c1:
    patient_name = st.text_input("Patient name", "")
with c2:
    patient_age = st.number_input("Age", min_value=1, max_value=120, value=33)
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
        placeholder="CBC, Hemoglobin 12.4 g/dL, Reference Range: 12.0 - 16.5..."
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
            res = find_test_with_value(combined, spec, int(patient_age))
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
