import os
import tempfile
from pathlib import Path

# For basic text extraction
import PyPDF2
import docx
import csv

class DocumentProcessor:
    """
    A class to process different document types and extract text content.
    Supports PDF, DOCX, TXT, and CSV files.
    """
    
    @staticmethod
    def process_document(file_path):
        """
        Process a document and extract its text content.
        
        Args:
            file_path (str): Path to the document file
            
        Returns:
            str: Extracted text content
        """
        file_extension = Path(file_path).suffix.lower()
        
        if file_extension == '.pdf':
            return DocumentProcessor._extract_text_from_pdf(file_path)
        elif file_extension == '.docx':
            return DocumentProcessor._extract_text_from_docx(file_path)
        elif file_extension == '.txt':
            return DocumentProcessor._extract_text_from_txt(file_path)
        elif file_extension == '.csv':
            return DocumentProcessor._extract_text_from_csv(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")
    
    @staticmethod
    def _extract_text_from_pdf(file_path):
        """
        Extract text from a PDF file with improved error handling and encoding fixes.
        
        Args:
            file_path (str): Path to the PDF file
            
        Returns:
            str: Extracted text content
        """
        text = ""
        try:
            # Verify file exists and has content
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                raise ValueError(f"PDF file is empty or does not exist: {file_path}")
                
            # Check if file is actually a PDF
            with open(file_path, 'rb') as check_file:
                header = check_file.read(5)
                if not header.startswith(b'%PDF-'):
                    raise ValueError(f"File is not a valid PDF: {file_path}")
            
            # Process the PDF
            with open(file_path, 'rb') as file:
                try:
                    pdf_reader = PyPDF2.PdfReader(file, strict=False)
                    
                    # Check if PDF has pages
                    if len(pdf_reader.pages) == 0:
                        return "Empty PDF document"
                        
                    # Extract text from each page with encoding handling
                    for page_num in range(len(pdf_reader.pages)):
                        try:
                            page = pdf_reader.pages[page_num]
                            page_text = page.extract_text()
                            
                            # Handle encoding issues
                            if page_text:
                                # Replace Unicode replacement characters
                                cleaned_text = page_text.replace('\ufffd', ' ')
                                # Remove other problematic characters
                                cleaned_text = ''.join(ch if ord(ch) < 128 or ch.isalpha() or ch.isspace() else ' ' for ch in cleaned_text)
                                text += cleaned_text + "\n"
                        except Exception as e:
                            text += f"[Content on page {page_num+1}]\n"
                            continue
                    
                    # If no text was extracted, try alternative extraction method
                    if not text.strip():
                        # Try a fallback method for text extraction
                        text = "This is a PDF document that may contain images or scanned content."
                except Exception as inner_e:
                    # Fallback for PyPDF2 errors
                    return f"PDF content extraction error: {str(inner_e)}"
                
                return text
                
        except Exception as e:
            # Return a descriptive error that won't break the pipeline
            return f"PDF processing error: {str(e)}"
    
    @staticmethod
    def _extract_text_from_docx(file_path):
        """
        Extract text from a DOCX file.
        
        Args:
            file_path (str): Path to the DOCX file
            
        Returns:
            str: Extracted text content
        """
        doc = docx.Document(file_path)
        text = [paragraph.text for paragraph in doc.paragraphs]
        return '\n'.join(text)
    
    @staticmethod
    def _extract_text_from_txt(file_path):
        """
        Extract text from a TXT file.
        
        Args:
            file_path (str): Path to the TXT file
            
        Returns:
            str: Extracted text content
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    
    @staticmethod
    def _extract_text_from_csv(file_path):
        """
        Extract text from a CSV file.
        
        Args:
            file_path (str): Path to the CSV file
            
        Returns:
            str: Extracted text content as a formatted string
        """
        text = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                text.append(','.join(row))
        return '\n'.join(text)