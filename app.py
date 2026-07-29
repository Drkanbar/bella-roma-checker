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

# Test definitions
BASE_TESTS = {
    "CBC": {
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
        ]
    },
    "Ferritin": {"strong": ["FERRITIN"]},
    "Iron": {"strong": ["IRON", "SERUM IRON", "TIBC", "TRANSFERRIN"]},
    "SGPT / ALT": {
        "strong": ["SGPT", "ALANINE AMINOTRANSFERASE", "ALANINE TRANSAMINASE"],
        "weak": ["ALT"],
    },
    "SGOT / AST": {
        "strong": ["SGOT", "ASPARTATE AMINOTRANSFERASE", "ASPARTATE TRANSAMINASE"],
        "weak": ["AST"],
    },
    "Urea": {"strong": ["UREA", "BLOOD UREA", "BUN"]},
    "Creatinine": {"strong": ["CREATININE", "CREATENINE"]},
    "PT / INR": {
        "strong": ["PROTHROMBIN TIME", "PROTHROMBIN", "INR"],
        "weak": ["PT"],
    },
    "APTT": {
        "strong": [
            "APTT",
            "PTT",
            "ACTIVATED PARTIAL THROMBOPLASTIN",
            "ACTIVATED PARTIAL",
        ]
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
        ]
    },
    "RBS / Glucose": {
        "strong": [
            "GLUCOSE",
            "RBS",
            "FBS",
            "RANDOM BLOOD SUGAR",
            "FASTING BLOOD SUGAR",
            "BLOOD SUGAR",
        ]
    },
    "TSH": {"strong": ["TSH", "THYROID STIMULATING HORMONE"]},
    "T3": {"strong": ["FREE T3", "FT3", "TRIIODOTHYRONINE"], "weak": ["T3"]},
    "T4": {"strong": ["FREE T4", "FT4", "THYROXINE"], "weak": ["T4"]},
    "HIV": {"strong": ["HIV", "HUMAN IMMUNODEFICIENCY"]},
    "HBsAg": {
        "strong": ["HBSAG", "HBS AG", "HEPATITIS B SURFACE", "HEPATITIS B"]
    },
    "Hepatitis C (HCV)": {"strong": ["HEPATITIS C", "HCV", "ANTI HCV"]},
    "CRP": {"strong": ["CRP", "C REACTIVE PROTEIN"]},
    "Sodium": {"strong": ["SODIUM", "NATRIUM"], "weak": ["NA+"]},
    "Potassium": {"strong": ["POTASSIUM", "KALIUM"], "weak": ["K+"]},
    "Calcium": {"strong": ["CALCIUM"]},
    "Magnesium": {"strong": ["MAGNESIUM"]},
}

PREGNANCY_TEST = {
    "Beta HCG (Pregnancy Test)": {
        "strong": [
            "BETA HCG",
            "B HCG",
            "HCG",
            "PREGNANCY TEST",
            "PREGNANCY",
        ]
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

def find_test(text: str, spec: dict):
    for kw in spec.get("strong", []):
        if re.search(keyword_pattern(kw), text):
            return kw
    for kw in spec.get("weak", []):
        for m in re.finditer(keyword_pattern(kw), text):
            if weak_hit_is_real(text, m):
                return kw
    return None

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
                return "", "HEIC not supported on this server (install pillow-heif)", False
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
                    return "", f"Unsupported file type ({ext or 'no extension'})", False
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
if "analyzed" not in st.session_state:
    st.session_state.analyzed = False

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
        help="PDF, JPG, PNG, WEBP, TIFF and HEIC all work. Select several at once."
    )
    pasted_text = st.text_area(
        "Or paste the report text here (fallback if your browser blocks uploads)",
        height=100,
        placeholder="CBC, Hemoglobin 12.4 g/dL, Ferritin 45..."
    )
    analyze = st.form_submit_button("Analyze reports", type="primary", use_container_width=True)

if analyze:
    st.session_state.analyzed = True
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
        found, missing = {}, []
        for name, spec in required.items():
            hit = find_test(combined, spec)
            if hit:
                found[name] = hit
            else:
                missing.append(name)

        st.divider()
        st.subheader("4. Audit result")
        done = len(found)
        st.progress(done / len(required), text=f"{done} of {len(required)} required tests found")

        col_found, col_missing = st.columns(2)
        with col_found:
            st.success(f"Found ({len(found)})")
            for name, kw in found.items():
                st.write(f"• {name} \n <span style='color:#888;font-size:0.8em'>({kw})</span>", unsafe_allow_html=True)
        with col_missing:
            if missing:
                st.error(f"Missing ({len(missing)})")
                for name in missing:
                    st.write(f"• **{name}**")
            else:
                st.success("Nothing missing")

        st.divider()
        if missing:
            st.warning(f"⚠️ {len(missing)} test(s) still needed before surgery.")
        else:
            st.success("✅ The file is complete — every required test is present.")

        summary = [
            "Pre-Surgery Lab Tests Checker",
            f"Patient: {patient_name or '-'} | Age: {int(patient_age)} | Gender: {patient_gender}",
            f"Files: {', '.join(d['name'] for d in docs.values())}",
            "",
            f"FOUND ({len(found)}):",
            *[f"• {n}" for n in found],
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
elif st.session_state.get("analyzed", False):
    st.warning("No readable text came out of these files. If they are photos, retake straight on in good light with the text filling the frame, or paste text into the box above.")
    
