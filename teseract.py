import cv2
import pytesseract
from PIL import Image
import numpy as np
import os
import re
from fuzzywuzzy import fuzz
import mysql.connector
import logging
from datetime import datetime

# Logging config
logging.basicConfig(level=logging.INFO)

# Corrections
custom_corrections = {
    "Tofal": "Total",
    "Fotal": "Total",
    "Toral": "Total",
    "Tetai": "Total",
    "casi": "Cash",
    "Chinge": "Change",
    "Chane": "Change",
    "Receipl": "Receipt",
    "Rectipt": "Receipt",
    "INVOICEE": "INVOICE",
    "NV": "INV",
    "TIIN": "TIN",
    "SABES": "SALES",
    "Elever": "Eleven",
    "Purpie": "Purple",
    "Chine": "Chinese",
    "Altamart": "Alfamart",
    "HARY": "MARY",
    "Sfhurburkss": "Starbucks",
    "Cotter": "Coffee",
    "AMOUKT": "Amount",
    "Subtota]": "Subtotal",
    "Subtota": "Subtotal",
    "SHAHARHA": "SHAWARMA",
    "TURK S": "TURK'S",
    "SH": "SM",
    "Tota!": "Total",
    "NOME": "HOME",
    "17": "IT",
    "Net Tota!": "Net Total"
}

known_stores = [
    "UNIQLO", "SM SUPERMARKET", "WATSONS", "7-ELEVEN", "JOLLIBEE",
    "MCDONALD'S", "STARBUCKS", "ROBINSONS", "MINISO", "NATIONAL BOOKSTORE",
    "SMSTORE", "SM STORE", "KENNY ROGERS ROASTERS", "EMILU'S MART", "Puregold", "JR ECONOVATION PEST CONTROL SERVICES",
    "Purple Chinese", "Alfamart", "ALFAMART, AMI BUHO", "Puregold Price Club, Inc.", "Cafe Mary Grace", "Ikano", "AYALA PROPERTY MANAGEMENT CORPORATION",
    "S&R PIZZA INC.", "KAMUNING BAKERY CORP", "Starbucks Coffee", "Chowking", "Turks Shawarma", "Erjohn & Almark Transit Corp", "Coco Fresh Tea & Juice",
    "Jollibee", "CHOWKING", "CHOWKING VERMOSA", "JOLLIBEE", "JOLLIBEE SM DASMARINAS", "ZUSPRESSO", "ACE Hardware", "Home It Yourself", "WATSONS", "NORTHERN STAR ENERGY",
    "Goldilocks", "Gong Cha", "WASHOKU KIKUFUJI", "SAVEMORE", "S&R", "SHELL", "ELECTROWORLD", "PREMIER SOUTHERN PETROLEUM", "COFFEE PROJECT", "JETTI"
]

category_keywords = {
    "Meals": ["KENNY ROGERS ROASTERS", "Starbucks", "Jollibee", "Mcdonald", "Starbucks Coffee", "Jollibee", "Chowking"],
    "medicine": ["WATSONS", "paracetamol", "drug", "capsule", "syrup", "Mercury Drugs"],
    "Convenience": ["candy", "soda", "Alfamart", "7-eleven", "snack"],
    "Grocery": ["Puregold", "SM SUPERMARKET", "ROBINSONS", "EMILU'S MART", "Puregold Price Club, Inc."],
    "Transportation": ["Erjohn & Almark Transit Corp", "AYALA PROPERTY MANAGEMENT CORPORATION"]
}

def clean_ocr_text(text):
    return re.sub(r'[^\x00-\x7F]+', '', text).strip()

def apply_custom_corrections(text, corrections):
    for wrong, right in corrections.items():
        text = re.sub(rf'\b{wrong}\b', right, text, flags=re.IGNORECASE)
    return text

def filter_lines(text):
    lines = text.splitlines()
    return "\n".join([line for line in lines if line.strip()])

def extract_vendor(text, known_stores):
    best_match = None
    best_score = 0
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        for store in known_stores:
            score = fuzz.partial_ratio(line.upper(), store.upper())
            if score > best_score and score > 80:
                best_score = score
                best_match = store
    return best_match

def extract_structured_info(text):
    data = {}
    lines = text.splitlines()
    first_lines = [line.strip() for line in lines[:10] if line.strip()]

    # Fuzzy match for store name
    best_match = None
    best_score = 0
    for line in first_lines:
        for store in known_stores:
            score = fuzz.ratio(line.upper(), store.upper())
            if score > best_score and score > 75:
                best_score = score
                best_match = store
    if best_match:
        data['vendor'] = extract_vendor(text, known_stores)

    # Date (convert to YYYY-MM-DD)
    date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?:\s+\d{1,2}:\d{2})?', text)
    if date_match:
        raw_date = date_match.group(1)
        date_formats = [
            "%d-%m-%Y", "%d/%m/%Y", "%m-%d-%Y", "%m/%d/%Y",
            "%d-%m-%y", "%d/%m/%y", "%m-%d-%y", "%m/%d/%y"
        ]
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(raw_date, fmt)
                data['date'] = parsed_date.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # Total (try multiple patterns)
    total_patterns = [
        # Priority 1 – Final totals (most accurate)
        r'\b(?:NET\s*TOTAL|TOTAL DUE|AMOUNT DUE|GRAND TOTAL|DINE[- ]IN TOTAL|TOTAL AMOUNT|TOTAL)\b[^\d]{0,20}?(?:\(\d+\))?[^\d]{0,10}?(?:PHP|Php|php|₱|P)?\s*(\d{1,6}(?:[.,]\d{1,2})?)',
        # Priority 2 – Cash paid
        r'\bCash Tendered\b[^\d]{0,10}(?:PHP|Php|php|₱|P)?\s*(\d{1,6}(?:[.,]\d{1,2})?)',
        # Priority 3 – Subtotals
        r'\bSUB[- ]?TOTAL\b[^\d]{0,10}(?:PHP|Php|php|₱|P)?\s*(\d{1,6}(?:[.,]\d{1,2})?)',
        r'\bSubtotal\b[^\d]{0,10}(?:PHP|Php|php|₱|P)?\s*(\d{1,6}(?:[.,]\d{1,2})?)',
    ]

    for pattern in total_patterns:
        total_match = re.search(pattern, text, re.IGNORECASE)
        if total_match:
            try:
                amount = total_match.group(1).replace(',', '')
                data['total'] = float(amount)
                break
            except ValueError:
                continue

    # Optional fallback: extract the largest amount (only if no total found)
    if 'total' not in data:
        amounts = re.findall(r'(\d{1,4}(?:[.,]\d{2}))', text)
        try:
            numbers = [float(a.replace(',', '')) for a in amounts]
            if numbers:
                data['total'] = max(numbers)
        except:
            pass

    # Category guess from keywords
    full_text = text.lower()
    for category, keywords in category_keywords.items():
        if any(kw in full_text for kw in keywords):
            data['category'] = category
            break
    else:
        data['category'] = "Expense"

    return data

def save_to_database(receipt_data):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="admin",
            password="123",
            database="csk"
        )
        cursor = conn.cursor()
        sql = '''
            INSERT INTO scanned_receipts (receipt_date, vendor, amount, category, image_path, raw_text, confidence_score, quality_flag)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        '''
        values = (
            receipt_data.get("date"),
            receipt_data.get("vendor"),
            receipt_data.get("total"),
            receipt_data.get("category"),
            receipt_data.get("image_path"),
            receipt_data.get("raw_text"),
            receipt_data.get("confidence"),
            receipt_data.get("quality")
        )
        cursor.execute(sql, values)
        conn.commit()
        logging.info("✅ Receipt saved to MySQL.")
    except mysql.connector.Error as err:
        logging.error(f"❌ DB Error: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# New: Save image to XAMPP uploads folder
def save_receipt_image(image_path, filename):
    destination_folder = r"F:\xampp\htdocs\csk\uploads\scanned"
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    destination_path = os.path.join(destination_folder, filename)
    try:
        # Copy the file to the destination
        with open(image_path, 'rb') as src, open(destination_path, 'wb') as dst:
            dst.write(src.read())
        logging.info(f"🖼️ Image saved to: {destination_path}")
    except Exception as e:
        logging.error(f"❌ Error saving image: {e}")

    # Return relative path for DB
    return f"../uploads/scanned/{filename}"


def ocr_with_tesseract(image_path):
    image = cv2.imread(image_path)
    if image is None:
        print(f"[!] Could not load image: {image_path}")
        return "", {}, 0, "Low"

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.medianBlur(gray, 3)
    thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # Get raw OCR text
    raw_text = pytesseract.image_to_string(thresh)
    cleaned = clean_ocr_text(raw_text)
    corrected = apply_custom_corrections(cleaned, custom_corrections)
    filtered = filter_lines(corrected)
    extracted = extract_structured_info(filtered)

    # Compute confidence
    ocr_data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
    confidences = [int(conf) for conf in ocr_data['conf'] if str(conf).isdigit()]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0
    quality_flag = "Low" if avg_conf < 50 else "Good" if avg_conf < 80 else "Very Good" if avg_conf < 90 else "Excellent"

    return filtered, extracted, avg_conf, quality_flag


def scan_folder(folder_path):
    supported_ext = ['.jpg', '.jpeg', '.png']
    for filename in os.listdir(folder_path):
        if any(filename.lower().endswith(ext) for ext in supported_ext):
            image_path = os.path.join(folder_path, filename)
            print(f"\n🔍 Scanning: {filename}")
            text, info, conf_score, quality_flag = ocr_with_tesseract(image_path)

            img_url = save_receipt_image(image_path, filename)
            info['image_path'] = img_url
            info['raw_text'] = text
            info['confidence'] = conf_score
            info['quality'] = quality_flag
            print("📄 OCR Result:\n", text)
            print("\n📌 Extracted Info:\n", info)
            save_to_database(info)
            print("------------------------------------------------")

# 📁 Folder path
folder_path = r"C:\Users\CEO Ivo John Barroba\Downloads\dataset\scan"
scan_folder(folder_path)
