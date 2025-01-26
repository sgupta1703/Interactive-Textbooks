import streamlit as st
import os
import csv
from PyPDF2 import PdfReader, PdfWriter
import pdfplumber
import re
from typing import Dict, Tuple
from PyPDF2.generic import (
    DictionaryObject, ArrayObject,
    NameObject, NumberObject, NullObject, RectangleObject
)
from PIL import Image
import fitz

def save_feedback_to_csv(name: str, email: str, feedback: str):
    file_path = "feedback.csv"
    file_exists = os.path.exists(file_path)
    
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Name", "Email", "Feedback"])
        writer.writerow([name, email, feedback])

def preview_pdf(pdf_path, num_pages=10):
    images = []
    doc = fitz.open(pdf_path)
    for i in range(min(num_pages, len(doc))):
        pix = doc[i].get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images

class TextbookLinker:
    def __init__(self, input_pdf_path: str):
        self.reader = PdfReader(input_pdf_path)
        self.writer = PdfWriter()
        self.pdf_path = input_pdf_path
        for page in self.reader.pages:
            self.writer.add_page(page)

    def _get_text_coordinates(self, page_num: int, number: str) -> Tuple[float, float, float, float]:
        with pdfplumber.open(self.pdf_path) as pdf:
            page = pdf.pages[page_num]
            words = page.extract_words(keep_blank_chars=True, use_text_flow=True)
            target = f"{number}."
            for word in words:
                if word['text'].strip().startswith(target):
                    page_height = page.height
                    x1, y1 = word['x0'], page_height - word['bottom']
                    x2, y2 = word['x1'], page_height - word['top']
                    padding = 4
                    return (x1 - padding, y1 - padding, x2 + padding, y2 + padding)
            return (0, 0, 0, 0)

    def find_problems_and_solutions(self, progress_callback=None) -> Dict[str, dict]:
        problems = {}
        in_solutions_section = False
        last_number = 0
        total_pages = len(PdfReader(self.pdf_path).pages)
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if progress_callback:
                    progress_callback(int((page_num / total_pages) * 50))
                text = page.extract_text()
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r'^(\d+)\.$', line.split()[0])
                    if match:
                        number = int(match.group(1))
                        if number == 1 and last_number > 50:
                            in_solutions_section = True
                        str_number = str(number)
                        if in_solutions_section:
                            if str_number in problems:
                                problems[str_number]['solution_page'] = page_num
                                problems[str_number]['solution_coords'] = self._get_text_coordinates(page_num, str_number)
                        else:
                            problems[str_number] = {
                                'problem_page': page_num,
                                'problem_coords': self._get_text_coordinates(page_num, str_number)
                            }
                            last_number = number
        return problems

    def add_links(self, problems: Dict[str, dict], progress_callback=None):
        total_problems = len(problems)
        for idx, (problem_num, locations) in enumerate(problems.items()):
            if 'problem_page' in locations and 'solution_page' in locations:
                problem_page = self.writer.pages[locations['problem_page']]
                solution_page = self.writer.pages[locations['solution_page']]
                problem_rect = RectangleObject(locations['problem_coords'])
                problem_link = DictionaryObject({
                    NameObject('/Type'): NameObject('/Annot'),
                    NameObject('/Subtype'): NameObject('/Link'),
                    NameObject('/Rect'): problem_rect,
                    NameObject('/F'): NumberObject(4),
                    NameObject('/Dest'): ArrayObject([
                        solution_page.indirect_reference,
                        NameObject('/XYZ'),
                        NullObject(),
                        NullObject(),
                        NullObject()
                    ]),
                    NameObject('/Border'): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)])
                })
                if '/Annots' in problem_page:
                    problem_page['/Annots'].append(problem_link)
                else:
                    problem_page[NameObject('/Annots')] = ArrayObject([problem_link])
                solution_rect = RectangleObject(locations['solution_coords'])
                solution_link = DictionaryObject({
                    NameObject('/Type'): NameObject('/Annot'),
                    NameObject('/Subtype'): NameObject('/Link'),
                    NameObject('/Rect'): solution_rect,
                    NameObject('/F'): NumberObject(4),
                    NameObject('/Dest'): ArrayObject([
                        problem_page.indirect_reference,
                        NameObject('/XYZ'),
                        NullObject(),
                        NullObject(),
                        NullObject()
                    ]),
                    NameObject('/Border'): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)])
                })
                if '/Annots' in solution_page:
                    solution_page['/Annots'].append(solution_link)
                else:
                    solution_page[NameObject('/Annots')] = ArrayObject([solution_link])
                if progress_callback:
                    progress_callback(50 + int((idx + 1) / total_problems * 50))

    def save(self, output_path: str):
        with open(output_path, 'wb') as output_file:
            self.writer.write(output_file)

st.title("📖 FastBook")
info_button = st.button('ℹ️ Info')

info_message = """
This application scans a textbook PDF for questions formatted as 'X. ' (number followed by a dot and space)
and hyperlinks them for easier navigation.
"""

if 'info_opened' not in st.session_state:
    st.session_state.info_opened = False

if info_button:
    st.session_state.info_opened = not st.session_state.info_opened

if st.session_state.info_opened:
    st.info(info_message)
    
st.sidebar.header("💬 Provide Feedback")
name = st.sidebar.text_input("Your Name")
email = st.sidebar.text_input("Your Email")
feedback = st.sidebar.text_area("Your Feedback", height=150)
if st.sidebar.button("Submit Feedback"):
    if name and email and feedback:
        save_feedback_to_csv(name, email, feedback)
        st.sidebar.success("Thank you for your feedback!")
    else:
        st.sidebar.warning("Please fill in all fields before submitting.")

uploaded_file = st.file_uploader("Upload a textbook PDF", type="pdf")
if uploaded_file:
    temp_pdf_path = "temp_uploaded.pdf"
    output_pdf_path = "linked_textbook.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(uploaded_file.read())
    with st.expander("Preview of Uploaded PDF"):
        images = preview_pdf(temp_pdf_path)
        for img in images:
            st.image(img, use_column_width=True)
    if st.button("Process PDF"):
        progress_bar = st.progress(0)
        linker = TextbookLinker(temp_pdf_path)
        problems = linker.find_problems_and_solutions(progress_bar.progress)
        linker.add_links(problems, progress_bar.progress)
        linker.save(output_pdf_path)
        progress_bar.progress(100)
        with open(output_pdf_path, "rb") as f:
            st.download_button("Download Linked PDF", data=f, file_name="linked_textbook.pdf", mime="application/pdf")
