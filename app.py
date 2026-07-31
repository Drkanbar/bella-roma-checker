import io
import os
import re
import hashlib
import streamlit as st
from PIL import Image, ImageOps
import pytesseract
import PyPDF2

# 1. Define the Pre-Operative Checklist (Required Tests)
# You can add or remove test names exactly as they appear in the lab reports.
REQUIRED_TESTS = [
    "Hb", "WBC", "PLT", "PT", "INR", "Creatinine", "Urea", "Na", "K", "Glucose"
]

def extract_text_from_pdf(uploaded_file):
    """Extracts raw text from the uploaded PDF document."""
    text = ""
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
    return text

def parse_lab_results(text, required_tests):
    """
    Scans the text for required tests, extracts their values and the reference 
    ranges provided in the file, and evaluates if they are normal or abnormal.
    """
    results = []
    
    for test in required_tests:
        # Regex explanation:
        # 1. (?i)\b({test})\b : Matches the exact test name (case-insensitive)
        # 2. .*? : Skips any characters (like spaces, dots, etc.)
        # 3. (\d+\.?\d*) : Captures the patient's result value (integer or decimal)
        # 4. .*? : Skips characters until the range
        # 5. (\d+\.?\d*)\s*-\s*(\d+\.?\d*) : Captures the Min range, a dash, and Max range
        pattern = rf"(?i)\b({test})\b.*?(\d+\.?\d*).*?(\d+\.?\d*)\s*-\s*(\d+\.?\d*)"
        
        match = re.search(pattern, text)
        
        if match:
            value = float(match.group(2))
            min_range = float(match.group(3))
            max_range = float(match.group(4))
            
            # Evaluate the extracted value against the extracted range
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
            # Test not found in the text
            results.append({
                "test": test.upper(),
                "value": "-",
                "range": "-",
                "status": "MISSING"
            })
            
    return results

def main():
    # Set up the Streamlit page layout and styling
    st.set_page_config(page_title="Pre-Op Lab Analyzer", page_icon="⚕️")
    
    st.title("Pre-Operative Lab Report Analyzer")
    st.write("Upload a patient's lab report (PDF) to verify required tests and detect abnormal values based on the report's embedded reference ranges.")
    
    # File Uploader
    uploaded_file = st.file_uploader("Upload Lab Report (PDF)", type=["pdf"])
    
    if uploaded_file is not None:
        with st.spinner("Analyzing document..."):
            extracted_text = extract_text_from_pdf(uploaded_file)
            
            if extracted_text:
                # Process the text
                analysis_results = parse_lab_results(extracted_text, REQUIRED_TESTS)
                
                st.subheader("Analysis Summary")
                st.markdown("---")
                
                # Categorize results
                abnormal = [r for r in analysis_results if r["status"] in ["HIGH", "LOW"]]
                missing = [r for r in analysis_results if r["status"] == "MISSING"]
                normal = [r for r in analysis_results if r["status"] == "NORMAL"]
                
                # 1. Display Missing Tests (Critical Priority)
                if missing:
                    st.error(f"⚠️ Missing Tests ({len(missing)})")
                    for item in missing:
                        st.write(f"- **{item['test']}**: Not found in the report.")
                
                # 2. Display Abnormal Tests (Out of Range)
                if abnormal:
                    st.warning(f"🚨 Out of Range Tests ({len(abnormal)})")
                    for item in abnormal:
                        direction = "🔺 HIGH" if item["status"] == "HIGH" else "🔻 LOW"
                        st.write(f"- **{item['test']}**: **{item['value']}** (Reference: {item['range']}) ➡️ {direction}")
                        
                # 3. Display Normal Tests (Collapsible)
                if normal:
                    with st.expander(f"✅ Normal Tests ({len(normal)})"):
                        for item in normal:
                            st.write(f"- **{item['test']}**: {item['value']} (Reference: {item['range']})")
                
                # Success message if everything is perfect
                if not abnormal and not missing and normal:
                    st.success("All required pre-operative tests are present and within normal limits.")

if __name__ == "__main__":
    main()
