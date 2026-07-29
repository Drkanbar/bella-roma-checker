import streamlit as st
from pypdf import PdfReader
from PIL import Image
import pytesseract
import re
import io
import fitz  # PyMuPDF

# إعداد واجهة التطبيق
st.set_page_config(page_title="مدقق فحوصات بيلا روما", layout="centered", page_icon="🩺")

st.title("🩺 مُدقّق فحوصات ما قبل الجراحة")
st.caption("النسخة المدعومة بالرفع المباشر والتصوير الفوري للجوال")

# 1. بيانات المريض
st.subheader("📋 1. بيانات المريض")
col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("اسم المريض / المريضة", "")
with col2:
    patient_age = st.number_input("العمر", min_value=1, max_value=120, value=25)
with col3:
    patient_gender = st.selectbox("الجنس", ["أنثى", "ذكر"])

# 2. القائمة المعتمدة للفحوصات
required_tests = {
    "CBC": ["CBC", "HEMOGLOBIN", "HAEMOGLOBIN", "COMPLETE BLOOD COUNT", "PLATELET", "WBC"],
    "Ferritin": ["FERRITIN"],
    "Iron": ["IRON", "SERUM IRON"],
    "SGPT / ALT (Alanine Aminotransferase)": ["SGPT", "ALT", "ALANINE AMINOTRANSFERASE"],
    "SGOT / AST (Aspartate Aminotransferase)": ["SGOT", "AST", "ASPARTATE AMINOTRANSFERASE"],
    "Urea": ["UREA", "BUN", "BLOOD UREA"],
    "Creatinine": ["CREATININE"],
    "PT": ["PT", "PROTHROMBIN TIME", "INR"],
    "APTT": ["APTT", "PTT", "ACTIVATED PARTIAL"],
    "Blood Group (ABO & Rh)": ["BLOOD GROUP", "ABO", "RH TYPE", "RH(D)", "RH FACTOR"],
    "HbA1c": ["HBA1C", "GLYCOSYLATED HEMOGLOBIN"],
    "RBS / Glucose (فحص السكر)": ["GLUCOSE", "RBS", "BLOOD GLUCOSE", "RANDOM BLOOD SUGAR", "RANDOM GLUCOSE", "FASTING GLUCOSE", "FBS"],
    "TSH": ["TSH", "THYROID STIMULATING"],
    "T3": ["T3", "FREE T3", "TRIIODOTHYRONINE"],
    "T4": ["T4", "FREE T4", "THYROXINE"],
    "HIV": ["HIV", "HUMAN IMMUNODEFICIENCY"],
    "HBsAg": ["HBSAG", "HEPATITIS B", "HBS AG"],
    "Hepatitis C": ["HEPATITIS C", "HCV", "ANTI-HCV", "ANTI HCV"],
    "CRP": ["CRP", "C-REACTIVE", "C REACTIVE PROTEIN"],
    "Sodium": ["Sodium".upper(), "NATRIUM"],
    "Potassium": ["POTASSIUM", "KALIUM"],
    "Calcium": ["CALCIUM"],
    "Magnesium": ["MAGNESIUM"],
}

if patient_gender == "أنثى" and patient_age < 80:
    required_tests["Beta HCG (فحص الحمل)"] = ["BETA HCG", "BETA-HCG", "HCG", "PREGNANCY", "B-HCG"]

if patient_age >= 40:
    required_tests["Chest X-ray (أشعة الصدر)"] = ["CHEST X-RAY", "CHEST XRAY", "CXR", "CHEST RADIOGRAPH"]
    required_tests["ECG with fitness clearance (تخطيط القلب)"] = ["ECG", "EKG", "ELECTROCARDIOGRAM", "CARDIOLOGY"]

# 3. إدخال المستندات (طريقتان: رفع ملف أو التقاط صورة بالكاميرا مباشرة)
st.divider()
st.subheader("📂 2. تقديم التقرير الطبي")

input_method = st.radio("اختر طريقة إدخال التقرير:", ["رفع ملف (PDF / صورة)", "التقاط صورة بالكميرا مباشرة 📸"])

uploaded_file = None
camera_file = None

if input_method == "رفع ملف (PDF / صورة)":
    uploaded_file = st.file_uploader("اختر التقرير من هاتف", type=["pdf", "PDF", "png", "PNG", "jpg", "JPG", "jpeg", "JPEG"])
else:
    camera_file = st.camera_input("التقاط صورة واضحة لورقة التحاليل")

extracted_text = ""
target_file = uploaded_file if uploaded_file is not None else camera_file

if target_file is not None:
    with st.spinner("جاري قراءة المعالجة واستخراج التحاليل..."):
        file_bytes = target_file.getvalue()
        filename = getattr(target_file, 'name', 'camera_image.jpg').lower()

        # أ) قراءة ملفات الـ PDF
        if filename.endswith('.pdf'):
            try:
                pdf_reader = PdfReader(io.BytesIO(file_bytes))
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        extracted_text += t + "\n"
            except Exception:
                pass

            if not extracted_text.strip():
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page in doc:
                        pix = page.get_pixmap(dpi=150)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        extracted_text += pytesseract.image_to_string(img) + "\n"
                except Exception:
                    pass

        # ب) قراءة الصور أو صور الكاميرا
        else:
            try:
                image = Image.open(io.BytesIO(file_bytes))
                image.thumbnail((1200, 1200))
                extracted_text += pytesseract.image_to_string(image) + "\n"
            except Exception:
                pass

        extracted_text_upper = extracted_text.upper()

        # المطابقة واستخراج النتائج
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
            if re.search(pattern, extracted_text_upper):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        st.divider()
        st.subheader("📊 3. نتيجة التدقيق")

        col_found, col_missing = st.columns(2)

        with col_found:
            st.success(f"✅ الفحوصات المتوفرة ({len(found_tests)})")
            for item in found_tests:
                st.write(f"• {item}")

        with col_missing:
            if missing_tests:
                st.error(f"❌ الفحوصات الناقصة ({len(missing_tests)})")
                for item in missing_tests:
                    st.write(f"• **{item}**")
            else:
                st.success("🎉 جميع الفحوصات المطلوبة متوفرة بالكامل!")

        st.divider()
        if missing_tests:
            st.warning(f"⚠️ **النتيجة:** ينقص التقرير {len(missing_tests)} تحليل/تحاليل لاستكمال الاعتماد.")
        else:
            st.success("✅ **النتيجة:** التقرير مكتمل ومستوفي لجميع متطلبات بيلا روما 100%.")

        with st.expander("🔍 معاينة النص المستخرج من الملف"):
            st.text(extracted_text if extracted_text.strip() else "لم يتم استخراج أي نص قابل للقراءة.")
