import streamlit as st
from pypdf import PdfReader
import re
import io

# محاولة تحميل مكتبات الصور بشكل آمن لكي لا ينهار التطبيق
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# إعداد واجهة التطبيق
st.set_page_config(page_title="مدقق فحوصات بيلا روما", layout="centered", page_icon="🩺")

st.title("🩺 مُدقّق فحوصات ما قبل الجراحة")
st.caption("نسخة مستقرة وآمنة لتدقيق التقارير الطبية")

# 1. بيانات المريض
st.subheader("📋 1. بيانات المريض")
col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("اسم المريض / المريضة", "")
with col2:
    patient_age = st.number_input("العمر", min_value=1, max_value=120, value=25)
with col3:
    patient_gender = st.selectbox("الجنس", ["أنثى", "ذكر"])

# 2. القائمة الطبية المعتمدة
required_tests = {
    "CBC": ["CBC", "HEMOGLOBIN", "HAEMOGLOBIN", "COMPLETE BLOOD COUNT", "PLATELET", "WBC"],
    "Ferritin": ["FERRITIN"],
    "Iron": ["IRON", "SERUM IRON"],
    "SGPT (ALT)": ["SGPT", "ALT", "ALANINE AMINOTRANSFERASE"],
    "SGOT (AST)": ["SGOT", "AST", "ASPARTATE AMINOTRANSFERASE"],
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
    "Sodium": ["SODIUM", "NATRIUM"],
    "Potassium": ["POTASSIUM", "KALIUM"],
    "Calcium": ["CALCIUM"],
    "Magnesium": ["MAGNESIUM"],
}

if patient_gender == "أنثى" and patient_age < 80:
    required_tests["Beta HCG (فحص الحمل)"] = ["BETA HCG", "BETA-HCG", "HCG", "PREGNANCY", "B-HCG"]

if patient_age >= 40:
    required_tests["Chest X-ray (أشعة الصدر)"] = ["CHEST X-RAY", "CHEST XRAY", "CXR", "CHEST RADIOGRAPH"]
    required_tests["ECG with fitness clearance (تخطيط القلب)"] = ["ECG", "EKG", "ELECTROCARDIOGRAM", "CARDIOLOGY"]

# 3. رفع المستندات
st.divider()
st.subheader("📂 2. رفع تقارير التحاليل")
uploaded_files = st.file_uploader(
    "اختر ملف الـ PDF أو الصورة", 
    type=["pdf", "PDF", "png", "PNG", "jpg", "JPG", "jpeg", "JPEG"], 
    accept_multiple_files=True
)

extracted_text = ""

if uploaded_files:
    with st.spinner("جاري قراءة الملفات..."):
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name.lower()

            # قراءة ملفات الـ PDF بأمان
            if filename.endswith('.pdf'):
                try:
                    pdf_reader = PdfReader(io.BytesIO(file_bytes))
                    for page in pdf_reader.pages:
                        t = page.extract_text()
                        if t:
                            extracted_text += t + "\n"
                except Exception as e:
                    st.warning(f"تعذر قراءة ملف الـ PDF: {uploaded_file.name}")

            # قراءة الصور بأمان
            else:
                if OCR_AVAILABLE:
                    try:
                        image = Image.open(io.BytesIO(file_bytes))
                        text = pytesseract.image_to_string(image)
                        extracted_text += text + "\n"
                    except Exception as e:
                        st.warning(f"تعذر قراءة الصورة (تحقق من تثبيت Tesseract): {uploaded_file.name}")
                else:
                    st.error("مكتبة قراءة الصور غير مفعلة على السيرفر.")

        extracted_text_upper = extracted_text.upper()

        # المطابقة مع الفحوصات المطلوبة
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
            if re.search(pattern, extracted_text_upper):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        # عرض النتائج
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
            st.success("✅ **النتيجة:** التقارير مكتملة ومستوفية 100%.")

        with st.expander("🔍 معاينة النص المستخرج"):
            st.text(extracted_text if extracted_text.strip() else "لم يتم استخراج أي نص من الملفات المحددة.")
