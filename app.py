import streamlit as st
from pypdf import PdfReader
from PIL import Image
import pytesseract
import re

# إعداد واجهة التطبيق
st.set_page_config(page_title="مدقق فحوصاتا", layout="centered", page_icon="🩺")

st.title("🩺 مُدقّق فحوصات ما قبل الجراحة (مُفصّل)")
st.caption("تدقيق تفصيلي لكل تحليل على حدة حسب ورقة مستشفى ")

# 1. بيانات المريض
st.subheader("📋 1. بيانات المريض")
col1, col2, col3 = st.columns(3)
with col1:
    patient_name = st.text_input("اسم المريض / المريضة", "")
with col2:
    patient_age = st.number_input("العمر", min_value=1, max_value=120, value=25)
with col3:
    patient_gender = st.selectbox("الجنس", ["أنثى", "ذكر"])

# 2. القائمة المعتمدة بعد تفكيك كل تحليل إلى بند منفصل تماماً
# 2. القائمة المعتمدة بعد تفكيك كل تحليل وإضافة كافة صيغ السكر (Glucose / RBS)
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
    
    # شامل لكل صيغ فحص السكر بالدم (Glucose, RBS, FBS, Blood Sugar)
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

# شرط فحص الحمل للإناث أقل من 80 سنة
if patient_gender == "أنثى" and patient_age < 80:
    required_tests["Beta HCG (فحص الحمل)"] = ["BETA HCG", "BETA-HCG", "HCG", "PREGNANCY", "B-HCG"]

# شرط الأشعة وتخطيط القلب للأعمار 40 سنة فأكثر
if patient_age >= 40:
    required_tests["Chest X-ray (أشعة الصدر)"] = ["CHEST X-RAY", "CHEST XRAY", "CXR", "CHEST RADIOGRAPH"]
    required_tests["ECG with fitness clearance (تخطيط القلب)"] = ["ECG", "EKG", "ELECTROCARDIOGRAM", "CARDIOLOGY"]

# 3. رفع المستندات
st.divider()
st.subheader("📂 2. رفع تقرير التحاليل (PDF أو صورة)")
uploaded_file = st.file_uploader("قم بسحب وإسقاط التقرير هنا أو اختر ملفاً", type=["pdf", "png", "jpg", "jpeg"])

extracted_text = ""

if uploaded_file is not None:
    with st.spinner("جاري قراءة الملف وتدقيق التحاليل تفصيلياً..."):
        # قراءة الـ PDF
        if uploaded_file.name.lower().endswith('.pdf'):
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
        # قراءة الصور
        else:
            try:
                image = Image.open(uploaded_file)
                extracted_text = pytesseract.image_to_string(image)
            except Exception as e:
                st.error("تعذر قراءة النص من الصورة، يرجى التأكد من وضوح المستند.")

        extracted_text_upper = extracted_text.upper()

        # المطابقة واستخراج النواقص
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            if any(re.search(r'\b' + re.escape(kw) + r'\b', extracted_text_upper) for kw in keywords):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        # عرض النتائج
        st.divider()
        st.subheader("📊 3. نتيجة التدقيق التفصيلي")

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

        # الخلاصة النهائية
        st.divider()
        if missing_tests:
            st.warning(f"⚠️ **النتيجة:** الملف ينقصه {len(missing_tests)} تحليل/تحاليل فردية لاستكمال الاعتماد.")
        else:
            st.success("✅ **النتيجة:** الملف مكتمل 100% ومستوفي لجميع تحاليل القائمة.")
