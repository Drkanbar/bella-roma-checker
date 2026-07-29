import streamlit as st
from pypdf import PdfReader
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import re
import io
import fitz  # PyMuPDF

# إعداد واجهة التطبيق
st.set_page_config(page_title="مدقق فحوصات بيلا روما", layout="centered", page_icon="🩺")

st.title("🩺 مُدقّق فحوصات ما قبل الجراحة")
st.caption("شامل لجميع أنواع المستندات، الصور، ولقطات الشاشة (Screenshots)")

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

def preprocess_image(pil_img):
    # تحويل الصورة وضبط الألوان للتعامل مع لقطات الشاشة
    img = pil_img.convert('RGB')
    # قص المساحات الفارغة التلقائية
    gray = img.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    return enhancer.enhance(1.8)

# 3. رفع المستندات (بدون تقييد الصدق الشكلي للامتدادات)
st.divider()
st.subheader("📂 2. رفع تقارير التحاليل")
uploaded_files = st.file_uploader(
    "رفع الصور أو لقطات الشاشة أو ملفات الـ PDF", 
    type=None,  # القبول العام لمنع الرفض بسب امتدادات الصور المختلفة
    accept_multiple_files=True
)

extracted_text = ""

if uploaded_files:
    with st.spinner(f"جاري قراءة {len(uploaded_files)} ملف/ملفات..."):
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name.lower()

            # معالجة الـ PDF
            if filename.endswith('.pdf'):
                pdf_text = ""
                try:
                    pdf_reader = PdfReader(io.BytesIO(file_bytes))
                    for page in pdf_reader.pages:
                        t = page.extract_text()
                        if t:
                            pdf_text += t + "\n"
                except Exception:
                    pass

                if not pdf_text.strip():
                    try:
                        doc = fitz.open(stream=file_bytes, filetype="pdf")
                        for page in doc:
                            pix = page.get_pixmap(dpi=200)
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            pdf_text += pytesseract.image_to_string(preprocess_image(img)) + "\n"
                    except Exception:
                        pass
                extracted_text += pdf_text + "\n"

            # معالجة كافة أنواع الصور ولقطات الشاشة
            else:
                try:
                    raw_image = Image.open(io.BytesIO(file_bytes))
                    processed = preprocess_image(raw_image)
                    
                    # محاولة القراءة الأولى
                    img_text = pytesseract.image_to_string(processed)
                    
                    # محاولة ثانية بالصورة الخام بدون معالجة في حال كانت لقطة شاشة دقيقة
                    if len(img_text.strip()) < 15:
                        img_text = pytesseract.image_to_string(raw_image)
                        
                    extracted_text += img_text + "\n"
                except Exception as e:
                    st.error(f"تعذر قراءة الملف: {uploaded_file.name}")

        extracted_text_upper = extracted_text.upper()

        # المطابقة
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
            if re.search(pattern, extracted_text_upper):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        # النتائج
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

        # الخلاصة
        st.divider()
        if missing_tests:
            st.warning(f"⚠️ **النتيجة:** ينقص التقرير {len(missing_tests)} تحليل/تحاليل لاستكمال الاعتماد.")
        else:
            st.success("✅ **النتيجة:** المستندات مستوفية 100%.")

        with st.expander("🔍 معاينة النص المستخرج من المستند"):
            st.text(extracted_text if extracted_text.strip() else "لم يتم العثور على أي نص القراءة.")
