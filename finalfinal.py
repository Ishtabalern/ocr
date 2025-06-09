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
    "SH": "SM", "FROPERTY": "PROPERTY", "SANAGENENT": "MANAGEMENT", "CORPORT": "CORPORATION"
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

def extract_vendor(text, known_stores, top_lines=10):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    best_match = None
    best_score = 0
    matched_line = ""
    for line in lines:
        for store in known_stores:
            score = fuzz.token_sort_ratio(line.upper(), store.upper())
            if score > best_score and score > 75:
                best_score = score
                best_match = store
                matched_line = line
    logging.info(f"🛒 Vendor match: {best_match} (matched line: '{matched_line}', score: {best_score})")
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
    data['vendor'] = extract_vendor(text, known_stores)

    # Date (convert to YYYY-MM-DD)
    date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
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
                data['date_confidence'] = 90  # Parsed successfully
                break
            except ValueError:
                continue
        if 'date' not in data:
            data['date'] = raw_date  # fallback
            data['date_confidence'] = 50

    # Total (try multiple patterns, take the *largest* valid match)
    # Enhanced total extraction logic
    pattern_weights = {
        r'\bGRAND TOTAL\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 100,
        r'\bNET TOTAL\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 95,
        r'\bTOTAL DUE\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 90,
        r'\bAMOUNT DUE\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 90,
        r'\bDINE[- ]IN TOTAL\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 90,
        r'\bAPP(?:ROVED)?(?:\s*AMOUNT)?[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 90,
        r'\b2US\s*APP\b[^\d]{0,10}(\d{1,6}(?:[.,]\d{2}))': 90,
        r'\bTOTAL\b[^\d]{0,15}(?:PHP|Php|php)?\s*(\d{1,6}(?:[.,]?\d{2}))': 85,
        r'\bSUB[- ]?TOTAL\b[^\d]{0,15}(?:PHP|Php|php)?\s*(\d{1,6}(?:[.,]?\d{2}))': 60,
        r'\bSubtotal\b[^\d]{0,15}(\d{1,6}(?:[.,]\d{2}))': 60,
        r'\bCash Tendered\s*(?:\+|:)?\s*(?:P)?\s*(\d{1,6}(?:[.,]\d{2}))': 70,
    }

    matched_totals = []

    for pattern, weight in pattern_weights.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                amount = float(match.replace(',', '').replace('O', '0'))
                matched_totals.append((amount, weight))
            except ValueError:
                continue

    if matched_totals:
        total_value, confidence = max(matched_totals, key=lambda x: x[0])  # pick largest
        data['total'] = total_value
        data['total_confidence'] = confidence
    else:
        # smarter fallback
        fallback_amounts = re.findall(r'(\d{1,6}(?:[.,]\d{2}))', text)
        try:
            numbers = [float(a.replace(',', '').replace('O', '0')) for a in fallback_amounts]
            if numbers:
                max_number = max(numbers)
                data['total'] = max_number

                # Heuristic confidence score based on how likely it is the true total
                if len(numbers) == 1:
                    data['total_confidence'] = 85
                elif max_number > 500:
                    data['total_confidence'] = 80
                elif max_number > 100:
                    data['total_confidence'] = 70
                else:
                    data['total_confidence'] = 50
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

    # ✅ Add confidence averaging here
    confidences = [
        data.get('vendor_confidence', 0),
        data.get('total_confidence', 0),
        data.get('date_confidence', 0),
    ]
    if any(confidences):
        data['confidence_score'] = round(sum(confidences) / len(confidences), 2)
    else:
        data['confidence_score'] = 0.0
    quality_flag = (
        "Low" if data['confidence_score'] < 50 else
        "Good" if data['confidence_score'] < 80 else
        "Very Good" if data['confidence_score'] < 90 else
        "Excellent"
    )

    return data, quality_flag


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
            INSERT INTO scanned_receipts (receipt_date, vendor, amount, category, image_path, raw_text, vendor_confidence, total_confidence, date_confidence, confidence_score, quality_flag)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        values = (
            receipt_data.get("date"),
            receipt_data.get("vendor"),
            receipt_data.get("total"),
            receipt_data.get("category"),
            receipt_data.get("image_path"),
            receipt_data.get("raw_text"),
            receipt_data.get('vendor_confidence', 0),
            receipt_data.get('total_confidence', 0),
            receipt_data.get('date_confidence', 0),
            receipt_data.get("confidence_score"),
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
        return "", {}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.medianBlur(gray, 3)
    thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    raw_text = pytesseract.image_to_string(thresh)
    cleaned = clean_ocr_text(raw_text)
    corrected = apply_custom_corrections(cleaned, custom_corrections)
    filtered = filter_lines(corrected)
    extracted = extract_structured_info(filtered)

    return filtered, extracted

def scan_folder(folder_path):
    supported_ext = ['.jpg', '.jpeg', '.png']
    for filename in os.listdir(folder_path):
        if any(filename.lower().endswith(ext) for ext in supported_ext):
            image_path = os.path.join(folder_path, filename)
            print(f"\n🔍 Scanning: {filename}")
            text, (info, quality_flag) = ocr_with_tesseract(image_path)

            img_url = save_receipt_image(image_path, filename)
            info['image_path'] = img_url
            info['raw_text'] = text
            info['quality'] = quality_flag
            print("📄 OCR Result:\n", text)
            print("\n📌 Extracted Info:\n", info)
            save_to_database(info)
            print("------------------------------------------------")


# 📁 Folder path
folder_path = r"C:\Users\CEO Ivo John Barroba\Downloads\dataset\scanned"
scan_folder(folder_path)
