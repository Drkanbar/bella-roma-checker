import streamlit as st
from pypdf import PdfReader
from PIL import Image
import pytesseract
import re
import io
import fitz  # PyMuPDF

# App Configuration
st.set_page_config(page_title="Bella Roma Checker", layout="centered", page_icon="🩺")

st.title("🩺 Pre-Surgery Lab Tests Checker")
st.caption("Cumulative Mobile Version - Upload files one by one easily")

# Initialize Session State for accumulation
if 'accumulated_text' not in st.session_state:
    st.session_state.accumulated_text = ""
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []

# 1. Patient Information
st.subheader("📋 1. Patient Information")
col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("Patient Name", "")
with col2:
    patient_age = st.number_input("Age", min_value=1, max_value=120, value=25)
with col3:
    patient_gender = st.selectbox("Gender", ["Female", "Male"])

# 2. Required Tests List
required_tests = {
    "CBC": ["CBC", "HEMOGLOBIN", "HAEMOGLOBIN", "COMPLETE BLOOD COUNT", "PLATELET", "WBC"],
    "Ferritin": ["FERRITIN"],
    "Iron": ["IRON", "SERUM IRON"],
    "SGPT / ALT": ["SGPT", "ALT", "ALANINE AMINOTRANSFERASE", "ALANINE AMINO TRANSFERASE", "ALANINE AMINO-TRANSFERASE"],
    "SGOT / AST": ["SGOT", "AST", "ASPARTATE AMINOTRANSFERASE", "ASPARTATE AMINO TRANSFERASE", "ASPARTATE AMINO-TRANSFERASE"],
    "Urea": ["UREA", "BUN", "BLOOD UREA"],
    "Creatinine": ["CREATININE"],
    "PT": ["PT", "PROTHROMBIN TIME", "INR"],
    "APTT": ["APTT", "PTT", "ACTIVATED PARTIAL"],
    "Blood Group (ABO & Rh)": ["BLOOD GROUP", "ABO", "RH TYPE", "RH(D)", "RH FACTOR"],
    "HbA1c": ["HBA1C", "GLYCOSYLATED HEMOGLOBIN"],
    "RBS / Glucose": ["GLUCOSE", "RBS", "BLOOD GLUCOSE", "RANDOM BLOOD SUGAR", "RANDOM GLUCOSE", "FASTING GLUCOSE", "FBS"],
    "TSH": ["TSH", "THYROID STIMULATING"],
    "T3": ["T3", "FREE T3", "TRIIODOTHYRONINE"],
    "T4": ["T4", "FREE T4", "THYROXINE"],
    "HIV": ["HIV", "HUMAN IMMUNODEFICIENCY"],
    "HBsAg": ["HBSAG", "HEPATITIS B", "HBS AG"],
    "Hepatitis C": ["HEPATITIS C", "HCV", "ANTI-HCV", "ANTI HCV"],
    "CRP": ["CRP", "C-REACTIVE", "C REACTIVE PROTEIN"],
    "Sodium": ["SODIUM", "NATRIUM"],
    "Potassium": ["POTASSIUM", "KALIUM"],
    "Calcium": ["CALCIUM"],
    "Magnesium": ["MAGNESIUM"],
}

# Conditional Tests
if patient_gender == "Female" and patient_age < 80:
    required_tests["Beta HCG (Pregnancy Test)"] = ["BETA HCG", "BETA-HCG", "HCG", "PREGNANCY", "B-HCG"]

if patient_age >= 40:
    required_tests["Chest X-ray"] = ["CHEST X-RAY", "CHEST XRAY", "CXR", "CHEST RADIOGRAPH"]
    required_tests["ECG"] = ["ECG", "EKG", "ELECTROCARDIOGRAM", "CARDIOLOGY"]

# 3. Cumulative File Uploader
st.divider()
st.subheader("📂 2. Upload Reports (One by One)")
st.info("💡 You can upload files sequentially. Each uploaded file will be automatically added to the evaluation.")

uploaded_file = st.file_uploader(
    "Choose a PDF or Image file", 
    type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name

    # Process only if it's a newly selected file
    if filename not in st.session_state.processed_files:
        with st.spinner(f"Processing {filename}..."):
            new_text = ""
            
            # A) Process PDFs
            if filename.lower().endswith('.pdf'):
                try:
                    pdf_reader = PdfReader(io.BytesIO(file_bytes))
                    for page in pdf_reader.pages:
                        t = page.extract_text()
                        if t:
                            new_text += t + "\n"
                    
                    if not new_text.strip():
                        doc = fitz.open(stream=file_bytes, filetype="pdf")
                        for page in doc:
                            pix = page.get_pixmap(dpi=120) 
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            new_text += pytesseract.image_to_string(img) + "\n"
                        doc.close()
                except Exception as e:
                    st.error(f"Error reading PDF: {str(e)}")

            # B) Process Images
            else:
                try:
                    img = Image.open(io.BytesIO(file_bytes))
                    img.thumbnail((1500, 1500))
                    new_text += pytesseract.image_to_string(img) + "\n"
                except Exception as e:
                    st.error(f"Error reading Image: {str(e)}")

            if new_text.strip():
                st.session_state.accumulated_text += "\n" + new_text
                st.session_state.processed_files.append(filename)
                st.success(f"Successfully added: {filename}")

# Display List of Processed Files & Reset Button
if st.session_state.processed_files:
    st.write("📁 **Successfully Uploaded Files:**")
    for f in st.session_state.processed_files:
        st.write(f"• {f}")
    
    if st.button("🗑️ Reset / Clear All Files"):
        st.session_state.accumulated_text = ""
        st.session_state.processed_files = []
        st.rerun()

# Logic Matching based on all accumulated texts
if st.session_state.accumulated_text.strip():
    extracted_text_upper = st.session_state.accumulated_text.upper().replace('\n', ' ')
    found_tests = []
    missing_tests = []

    for test_name, keywords in required_tests.items():
        pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
        if re.search(pattern, extracted_text_upper):
            found_tests.append(test_name)
        else:
            missing_tests.append(test_name)

    st.divider()
    st.subheader("📊 3. Cumulative Audit Result")

    col_found, col_missing = st.columns(2)

    with col_found:
        st.success(f"✅ Found Tests ({len(found_tests)})")
        for item in found_tests:
            st.write(f"• {item}")

    with col_missing:
        if missing_tests:
            st.error(f"❌ Missing Tests ({len(missing_tests)})")
            for item in missing_tests:
                st.write(f"• **{item}**")
        else:
            st.success("🎉 All required tests are available!")

    st.divider()
    if missing_tests:
        st.warning(f"⚠️ **Result:** The reports are missing {len(missing_tests)} test(s).")
    else:
        st.success("✅ **Result:** All reports combined are 100% complete and meet requirements.")

    with st.expander("🔍 View All Accumulated Raw Text"):
        st.text(st.session_state.accumulated_text)
else:
    st.warning("⚠️ Please upload at least one file to begin analysis.")
