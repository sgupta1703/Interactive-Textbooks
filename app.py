import streamlit as st
import os
import csv
from PyPDF2 import PdfReader, PdfWriter
import pdfplumber
import re
from typing import Dict, Tuple
from PyPDF2.generic import DictionaryObject, ArrayObject, NameObject, NumberObject, NullObject, RectangleObject
from PIL import Image
import fitz
import pandas as pd

# Function to append feedback to a CSV file
def save_feedback_to_csv(name: str, email: str, feedback: str):
    file_path = "feedback.csv"
    file_exists = os.path.exists(file_path)
    
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Name", "Email", "Feedback"])
        writer.writerow([name, email, feedback])

# Function to preview the PDF as images
def preview_pdf(pdf_path, num_pages=10):
    images = []
    doc = fitz.open(pdf_path)
    for i in range(min(num_pages, len(doc))):
        pix = doc[i].get_pixmap()
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
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
            words = page.extract_words(keep_blank_chars=True, use_text_flow=True) or []
            target = f"{number}."
            for word in words:
                if word['text'].strip().startswith(target):
                    page_height = page.height
                    x1, y1 = word['x0'], page_height - word['bottom']
                    x2, y2 = word['x1'], page_height - word['top']
                    padding = 4
                    return (x1 - padding, y1 - padding, x2 + padding, y2 + padding)
            return (0, 0, 0, 0)

    def find_problems_and_solutions(self, problem_patterns: list, solution_patterns: list, start_page=0, end_page=None) -> Dict[str, dict]:
        problems = {}
        with pdfplumber.open(self.pdf_path) as pdf:
            pages = pdf.pages[start_page:end_page] if end_page else pdf.pages[start_page:]
            for page_num, page in enumerate(pages, start=start_page):
                text = page.extract_text()
                if not text:
                    continue
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    for pattern in problem_patterns:
                        if re.search(pattern, line):
                            number = self.extract_number_from_line(line)
                            if number:
                                str_number = str(number)
                                if str_number not in problems:
                                    problems[str_number] = {'problem_page': page_num, 'problem_coords': self._get_text_coordinates(page_num, str_number)}
                    for pattern in solution_patterns:
                        if re.search(pattern, line):
                            number = self.extract_number_from_line(line)
                            if number:
                                str_number = str(number)
                                if str_number in problems:
                                    problems[str_number].update({'solution_page': page_num, 'solution_coords': self._get_text_coordinates(page_num, str_number)})
        return problems

    def extract_number_from_line(self, line: str):
        match = re.search(r'\b(\d+)\b', line)
        if match:
            return int(match.group(1))
        return None

    def add_links(self, problems: Dict[str, dict]):
        for problem_num, locations in problems.items():
            if 'problem_page' in locations and 'solution_page' in locations:
                problem_page = self.writer.pages[locations['problem_page']]
                solution_page = self.writer.pages[locations['solution_page']]
                rect = RectangleObject(locations['problem_coords'])

                # Ensure indirect reference exists
                if not solution_page.indirect_reference:
                    solution_page.indirect_reference = self.writer._add_object(solution_page)

                # Add annotation using PyPDF2's annotation system
                self.writer.add_annotation(
                    locations['problem_page'],
                    {
                        "/Subtype": "/Link",
                        "/Rect": rect,
                        "/Border": [0, 0, 0],
                        "/Dest": [solution_page.indirect_reference, "/XYZ", None, None, None]
                    }
                )

    def save(self, output_path: str):
        with open(output_path, "wb") as output_file:
            self.writer.write(output_file)

# Streamlit app setup
st.set_page_config(page_title="Textbook Problem Linker", layout="wide")

st.title("📖 Interactive Textbook Problem Linker")
info_button = st.button('ℹ️ Info')

info_message = """
This application allows you to upload a textbook PDF and specify problem-solution patterns. 
It will generate a linked PDF where problem numbers hyperlink to their solutions.
"""

if 'info_opened' not in st.session_state:
    st.session_state.info_opened = False

if info_button:
    st.session_state.info_opened = not st.session_state.info_opened

if st.session_state.info_opened:
    st.info(info_message)

# Feedback form
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

# PDF file upload
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

    # Two-column layout for problem and solution checkboxes
    st.header("Select Patterns for Problem and Solution Matching")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Problem Patterns")
        problem_patterns = ["1\\.", "#1", "Problem 1", "Question 1", "Exercise 1"]
        selected_problems = [pattern for i, pattern in enumerate(problem_patterns) if st.checkbox(pattern, key=f"problem_{i}")]

    with col2:
        st.subheader("Solution Patterns")
        solution_patterns = ["1\\.", "#1", "Problem 1", "Question 1", "Exercise 1", "Solution 1", "Answer 1"]
        selected_solutions = [pattern for i, pattern in enumerate(solution_patterns) if st.checkbox(pattern, key=f"solution_{i}")]

    if st.button("Process PDF"):
        progress_bar = st.progress(0)
        with st.status("Processing PDF...") as status:
            linker = TextbookLinker(temp_pdf_path)
            problems = linker.find_problems_and_solutions(selected_problems, selected_solutions)
            progress_bar.progress(50)
            
            if problems:
                linker.add_links(problems)
                linker.save(output_pdf_path)
                progress_bar.progress(100)
                status.update(label="Processing complete!", state="complete")
                with open(output_pdf_path, "rb") as f:
                    st.download_button("Download Linked PDF", data=f, file_name="linked_textbook.pdf", mime="application/pdf")
            else:
                st.warning("No problems found in the uploaded PDF.")
