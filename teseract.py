import os
import re
import cv2
import pytesseract
import mysql.connector
import pandas as pd
import nltk
import shutil
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
from concurrent.futures import ThreadPoolExecutor

# Set up Tesseract path (for Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Rule-Based Categories
RULE_BASED_CATEGORIES = {
    "Food & Groceries": ["grocery", "supermarket", "food", "restaurant", "dining", "cafe", "pizza", "bakery",
                         "starbucks", "puregold", "7/11", "robinsons supermarket", "s&r", "easy day shop"],
    "Utilities": ["electric", "water", "gas", "internet", "phone", "cable", "pldt", "globe", "meralco", "maynilad"],
    "Transportation": ["taxi", "uber", "train", "bus", "fuel", "grab"],
    "Entertainment": ["movie", "concert", "game", "entertainment", "music"],
    "Clothes": ["smstore", "uniqlo", "uniolo", "oxygen"],
    "Healthcare": ["pharmacy", "hospital", "clinic", "medical", "mercury drug"],
    "Miscellaneous": []
}

TRAINING_DATA = [
    {"text": "Gas at Shell Station", "category": "Transportation"},
    {"text": "Dinner at McDonald's", "category": "Food & Groceries"},
    {"text": "Electricity Bill", "category": "Utilities"},
    {"text": "Concert Ticket", "category": "Entertainment"},
    {"text": "Pharmacy Purchase", "category": "Healthcare"},
]

# Preprocessing for ML-Based Categorization
def preprocess_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    tokens = nltk.word_tokenize(text)
    return ' '.join(tokens)

# Train ML-Based Model
def train_ml_model(data):
    df = pd.DataFrame(data)
    vectorizer = TfidfVectorizer(preprocessor=preprocess_text)
    X = vectorizer.fit_transform(df['text'])
    return vectorizer, X, df['category']

# ML-Based Categorization
def ml_categorize(text, vectorizer, X, categories):
    processed_text = preprocess_text(text)
    input_vector = vectorizer.transform([processed_text])
    similarity = cosine_similarity(input_vector, X)
    best_match_index = similarity.argmax()
    return categories.iloc[best_match_index]

# Hybrid Categorization
def categorize_receipt(vendor, description, vectorizer, X, categories):
    combined_text = f"{vendor} {description}".lower()
    for category, keywords in RULE_BASED_CATEGORIES.items():
        if any(keyword in combined_text for keyword in keywords):
            return category

    return ml_categorize(combined_text, vectorizer, X, categories)

# Preprocess Image
def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        logging.warning(f"Unable to read image: {image_path}")
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return thresh

# Perform OCR
def perform_ocr(image):
    try:
        return pytesseract.image_to_string(Image.fromarray(image))
    except Exception as e:
        logging.error(f"Error during OCR: {e}")
        return ""

# Extract Details from Text
def extract_details(ocr_text):
    date = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2})\b", ocr_text)
    total = re.search(r"(?:Total|Amount Due|Grand Total|Total Due)[\s:]*[₱$€]?(\d+[.,]?\d{2})", ocr_text, re.IGNORECASE)
    lines = ocr_text.split("\n")
    vendor = "Unknown"

    for line in lines:
        if len(line.strip()) > 3 and not any(keyword in line.lower() for keyword in ["total", "amount", "date"]):
            vendor = line.strip()
            break

    return {
        "date": date.group(0) if date else "Unknown",
        "vendor": vendor,
        "total": total.group(1) if total else "0.00"
    }

# Save to Database
def save_to_database(receipt_data):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="cskdb"
        )
        cursor = conn.cursor()
        sql = '''
            INSERT INTO receipts (date, vendor, total, category)
            VALUES (%s, %s, %s, %s)
        '''
        values = (receipt_data["date"], receipt_data["vendor"], receipt_data["total"], receipt_data["category"])
        cursor.execute(sql, values)
        conn.commit()
        logging.info("Receipt saved to MySQL database.")
    except mysql.connector.Error as err:
        logging.error(f"Database error: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Process Receipt Image
def process_receipt(image_path, vectorizer, X, categories, converted_folder):
    processed_image = preprocess_image(image_path)
    if processed_image is None:
        return

    ocr_text = perform_ocr(processed_image)
    if not ocr_text.strip():
        logging.warning(f"No text detected in image: {image_path}")
        return

    receipt_data = extract_details(ocr_text)
    receipt_data["category"] = categorize_receipt(receipt_data["vendor"], ocr_text, vectorizer, X, categories)
    save_to_database(receipt_data)

    # Move the file to the converted folder
    try:
        if not os.path.exists(converted_folder):
            os.makedirs(converted_folder)  # Create the folder if it doesn't exist
        shutil.move(image_path, os.path.join(converted_folder, os.path.basename(image_path)))
        logging.info(f"Moved file to {converted_folder}: {image_path}")
    except Exception as e:
        logging.error(f"Error moving file {image_path} to {converted_folder}: {e}")

# Main Function
def main():
    folder_path = 'C:/Users/CEO Ivo John Barroba/Downloads/dataset/scanned'
    converted_folder = 'C:/Users/CEO Ivo John Barroba/Downloads/dataset/converted'
    vectorizer, X, categories = train_ml_model(TRAINING_DATA)

    with ThreadPoolExecutor() as executor:
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_path = os.path.join(folder_path, filename)
                executor.submit(process_receipt, image_path, vectorizer, X, categories, converted_folder)

if __name__ == "__main__":
    main()
