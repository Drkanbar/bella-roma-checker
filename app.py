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
st.caption("نسخة مستقرة تدعم معالجة الصور المتعددة وملفات PDF بكفاءة على الجوال")

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

# 3. رفع التقارير المتعددة
st.divider()
st.subheader("📂 2. رفع تقارير التحاليل")

# السماح برفع عدة ملفات في نفس الوقت
uploaded_files = st.file_uploader(
    "اختر ملفات PDF أو صور متعددة من جوالك", 
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True
)

all_extracted_text = ""

if uploaded_files:
    total_files = len(uploaded_files)
    st.info(f"تم اختيار {total_files} ملف/ملفات. جاري المعالجة...")
    
    # شريط تقدم لمتابعة حالة المعالجة بوضوح
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        file_bytes = file.getvalue()
        filename = file.name.lower()
        
        # أ) معالجة ملفات الـ PDF
        if filename.endswith('.pdf'):
            try:
                pdf_reader = PdfReader(io.BytesIO(file_bytes))
                pdf_text = ""
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        pdf_text += t + "\n"
                
                # إذا كان الـ PDF عبارة عن صور (سكينر) ولا يوجد نص
                if not pdf_text.strip():
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    for page in doc:
                        # تقليل الدقة قليلاً للحفاظ على ذاكرة الجوال
                        pix = page.get_pixmap(dpi=120) 
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        pdf_text += pytesseract.image_to_string(img) + "\n"
                    doc.close() # تفريغ الذاكرة
                
                all_extracted_text += pdf_text
                
            except Exception as e:
                st.error(f"حدث خطأ أثناء قراءة ملف الـ PDF ({filename}): {str(e)}")

        # ب) معالجة الصور
        else:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                # تصغير الصورة إذا كانت ضخمة جداً لتجنب تعليق الجوال
                img.thumbnail((1500, 1500))
                all_extracted_text += pytesseract.image_to_string(img) + "\n"
            except Exception as e:
                st.error(f"حدث خطأ أثناء قراءة الصورة ({filename}): {str(e)}")
        
        # تحديث شريط التقدم بعد إنجاز كل ملف
        progress_bar.progress((i + 1) / total_files)

    st.success("تم الانتهاء من قراءة جميع الملفات!")

    # المطابقة واستخراج النتائج
    if all_extracted_text.strip():
        extracted_text_upper = all_extracted_text.upper()
        found_tests = []
        missing_tests = []

        for test_name, keywords in required_tests.items():
            pattern = r'(' + '|'.join([re.escape(kw) for kw in keywords]) + r')'
            if re.search(pattern, extracted_text_upper):
                found_tests.append(test_name)
            else:
                missing_tests.append(test_name)

        st.divider()
        st.subheader("📊 3. نتيجة التدقيق الشاملة")

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
            st.warning(f"⚠️ **النتيجة:** ينقص التقارير المرفوعة {len(missing_tests)} تحليل/تحاليل لاستكمال الاعتماد.")
        else:
            st.success("✅ **النتيجة:** التقارير مكتملة ومستوفية لجميع متطلبات بيلا روما 100%.")

        with st.expander("🔍 معاينة النص المستخرج من جميع الملفات"):
            st.text(all_extracted_text)
    else:
        st.warning("⚠️ لم يتم استخراج أي نصوص من الملفات المرفوعة.")
