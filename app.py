import streamlit as st
import re
from pypdf import PdfReader

# 1. Define the Pre-Operative Checklist (Required Tests)
REQUIRED_TESTS = [
    "Hb", "WBC", "PLT", "PT", "INR", "Creatinine", "Urea", "Na", "K", "Glucose"
]

def extract_text_from_pdf(uploaded_file):
    """Extracts raw text from the uploaded PDF document using the modern pypdf library."""
    text = ""
    try:
        reader = PdfReader(uploaded_file)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
    return text

def parse_lab_results(text, required_tests):
    """
    Scans the extracted text for required tests, matches their values and 
    reference ranges, and evaluates if they are out of range.
    """
    results = []
    
    for test in required_tests:
        # Regex pattern matching:
        # Test Name -> Result Value -> Min Range - Max Range
        pattern = rf"(?i)\b({test})\b.*?(\d+\.?\d*).*?(\d+\.?\d*)\s*-\s*(\d+\.?\d*)"
        
        match = re.search(pattern, text)
        
        if match:
            value = float(match.group(2))
            min_range = float(match.group(3))
            max_range = float(match.group(4))
            
            status = "NORMAL"
            if value < min_range:
                status = "LOW"
            elif value > max_range:
                status = "HIGH"
                
            results.append({
                "test": test.upper(),
                "value": value,
                "range": f"{min_range} - {max_range}",
                "status": status
            })
        else:
            results.append({
                "test": test.upper(),
                "value": "-",
                "range": "-",
                "status": "MISSING"
            })
            
    return results

def main():
    st.set_page_config(page_title="Pre-Op Lab Analyzer", page_icon="⚕️")
    
    st.title("Pre-Operative Lab Report Analyzer")
    st.write("Upload a patient's lab report (PDF) to verify required tests and detect abnormal values based on the report's embedded reference ranges.")
    
    uploaded_file = st.file_uploader("Upload Lab Report (PDF)", type=["pdf"])
    
    if uploaded_file is not None:
        with st.spinner("Analyzing document..."):
            extracted_text = extract_text_from_pdf(uploaded_file)
            
            if extracted_text:
                analysis_results = parse_lab_results(extracted_text, REQUIRED_TESTS)
                
                st.subheader("Analysis Summary")
                st.markdown("---")
                
                abnormal = [r for r in analysis_results if r["status"] in ["HIGH", "LOW"]]
                missing = [r for r in analysis_results if r["status"] == "MISSING"]
                normal = [r for r in analysis_results if r["status"] == "NORMAL"]
                
                # 1. Missing Tests
                if missing:
                    st.error(f"⚠️ Missing Tests ({len(missing)})")
                    for item in missing:
                        st.write(f"- **{item['test']}**: Not found in the report.")
                
                # 2. Out of Range Tests
                if abnormal:
                    st.warning(f"🚨 Out of Range Tests ({len(abnormal)})")
                    for item in abnormal:
                        direction = "🔺 HIGH" if item["status"] == "HIGH" else "🔻 LOW"
                        st.write(f"- **{item['test']}**: **{item['value']}** (Reference: {item['range']}) ➡️ {direction}")
                        
                # 3. Normal Tests
                if normal:
                    with st.expander(f"✅ Normal Tests ({len(normal)})"):
                        for item in normal:
                            st.write(f"- **{item['test']}**: {item['value']} (Reference: {item['range']})")
                
                if not abnormal and not missing and normal:
                    st.success("All required pre-operative tests are present and within normal limits.")

if __name__ == "__main__":
    main()
