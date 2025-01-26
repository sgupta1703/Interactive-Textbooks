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
import pandas as pd

def save_feedback_to_csv(name: str, email: str, feedback: str):
    file_path = "feedback.csv"
    file_exists = os.path.exists(file_path)
    
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Name", "Email", "Feedback"])  # Write headers if the file is new
        writer.writerow([name, email, feedback])

# Function to preview the PDF as images
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

    def find_problems_and_solutions(self, start_page=0, end_page=None, progress_callback=None) -> Dict[str, dict]:
        problems = {}
        in_solutions_section = False
        last_number = 0
        with pdfplumber.open(self.pdf_path) as pdf:
            pages = pdf.pages[start_page:end_page] if end_page else pdf.pages[start_page:]
            total_pages = len(pages)

            for idx, page in enumerate(pages, start=start_page):
                text = page.extract_text()
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    first_word = line.split()[0] if line.split() else ''
                    match = re.match(r'^(\d+)\.$', first_word)
                    if match:
                        number = int(match.group(1))
                        if number == 1 and last_number > 50:
                            in_solutions_section = True
                        if in_solutions_section:
                            str_number = str(number)
                            if str_number in problems:
                                problems[str_number]['solution_page'] = idx
                                problems[str_number]['solution_coords'] = self._get_text_coordinates(idx, str_number)
                        else:
                            str_number = str(number)
                            problems[str_number] = {
                                'problem_page': idx,
                                'problem_coords': self._get_text_coordinates(idx, str_number)
                            }
                            last_number = number
                
                # **Update progress bar after each page**
                if progress_callback:
                    progress_callback(int((idx - start_page + 1) / total_pages * 50))  # Scale progress to 50%

        return problems

    def add_links(self, problems: Dict[str, dict], progress_callback=None):
        total_problems = len(problems)
        for idx, (problem_num, locations) in enumerate(problems.items()):
            if 'problem_page' in locations and 'solution_page' in locations:
                problem_page = self.writer.pages[locations['problem_page']]
                solution_page = self.writer.pages[locations['solution_page']]
                rect = RectangleObject(locations['problem_coords'])
                problem_link = DictionaryObject({
                    NameObject('/Type'): NameObject('/Annot'),
                    NameObject('/Subtype'): NameObject('/Link'),
                    NameObject('/Rect'): rect,
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

            if progress_callback:
                progress_callback(50 + int((idx + 1) / total_problems * 25)) 

    def save(self, output_path: str):
        with open(output_path, 'wb') as output_file:
            self.writer.write(output_file)

st.set_page_config(page_title="Textbook Problem Linker", layout="wide")

st.title("📖 FastBook")
info_button = st.button('ℹ️ Info')

info_message = """
This application allows you to upload a PDF of your textbook, automatically finds the problems and their solutions, 
and then creates clickable links on the numbers of the problem and the corresponding solution within the document. 
Simply upload a PDF, let the tool process the content, and download the updated version with clickable links!
"""

if 'info_opened' not in st.session_state:
    st.session_state.info_opened = False

if info_button:
    st.session_state.info_opened = not st.session_state.info_opened

if st.session_state.info_opened:
    st.info(info_message)
else:
    st.empty()

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

        def update_progress(value):
            progress_bar.progress(value)

        with st.status("Processing PDF...") as status:
            linker = TextbookLinker(temp_pdf_path)
            problems = linker.find_problems_and_solutions(0, None, progress_callback=update_progress)
            
            if problems:
                linker.add_links(problems, progress_callback=update_progress)
                update_progress(90) 
                linker.save(output_pdf_path)
                update_progress(100) 
                
                status.update(label="Processing complete!", state="complete")
                with open(output_pdf_path, "rb") as f:
                    st.download_button("Download Linked PDF", data=f, file_name="linked_textbook.pdf", mime="application/pdf")
            else:
                st.warning("No problems found in the uploaded PDF.")
