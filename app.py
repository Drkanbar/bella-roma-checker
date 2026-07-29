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
st.caption("Stable English Version - Optimized for Mobile Reliability")

# 1. Patient Information
st.subheader("📋 1. Patient Information")
col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("Patient Name", "")
with col2:
    patient_age = st.number_input("Age", min_value=1, max_value=120, value=25)
with col3:
    patient_gender = st.selectbox("Gender", ["Female", "Male"])

# 2. Required Tests List (Updated for better OCR matching)
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

# 3. Upload Reports
st.divider()
st.subheader("📂 2. Upload Medical Reports")

uploaded_files = st.file_uploader(
    "Choose PDF files or Images (Multiple allowed)", 
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True
)

all_extracted_text = ""

if uploaded_files:
    total_files = len(uploaded_files)
    st.info(f"Processing {total_files} file(s). Please wait...")
    
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        file_bytes = file.getvalue()
        filename = file.name.lower()
        
        # A) Process PDFs
        if filename.endswith('.pdf'):
            try:
                pdf_reader = PdfReader(io.BytesIO(file_bytes))
                pdf_text = ""
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        pdf_text += t + "\n"
                
                # If PDF is scanned (no text), use PyMuPDF and OCR
                if not pdf_text.strip():
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page in doc:
                        pix = page.get_pixmap(dpi=120) 
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        pdf_text += pytesseract.image_to_string(img) + "\n"
                    doc.close()
                
                all_extracted_text += pdf_text
                
            except Exception as e:
                st.error(f"Error reading PDF ({filename}): {str(e)}")

        # B) Process Images
        else:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                img.thumbnail((1500, 1500))
                all_extracted_text += pytesseract.image_to_string(img) + "\n"
            except Exception as e:
                st.error(f"Error reading Image ({filename}): {str(e)}")
        
        # Update progress bar
        progress_bar.progress((i + 1) / total_files)

    st.success("All files processed successfully!")

    # Logic Matching (Ignore newlines during matching to catch split words)
    if all_extracted_text.strip():
        # Replace newlines with spaces so words split across lines are matched correctly
        extracted_text_upper = all_extracted_text.upper().replace('\n', ' ')
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
            if re.search(pattern, extracted_text_upper):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        st.divider()
        st.subheader("📊 3. Final Audit Result")

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
            st.warning(f"⚠️ **Result:** The report is missing {len(missing_tests)} test(s).")
        else:
            st.success("✅ **Result:** The report is 100% complete and meets all requirements.")

        with st.expander("🔍 View Extracted Raw Text"):
            st.text(all_extracted_text)
    else:
        st.warning("⚠️ No readable text was found in the uploaded files.")
