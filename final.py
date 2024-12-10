import os
import re
import cv2
import pytesseract
import mysql.connector
import pandas as pd
import nltk
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Set up Tesseract path (for Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Rule-Based Categories
RULE_BASED_CATEGORIES = {
    "Food & Groceries": ["grocery", "supermarket", "food", "restaurant", "dining", "cafe", "pizza", "bakery",
                         "smsupermarket", "starbucks", "starbucks coffee", "dali", "dali everyday grocery", "7/11", "robinsons supermarket", "puremart", "easy day shop", "s&r", "s & r",
                         "emilu's mart", "puregold", "super8", "super 8"],
    "Utilities": ["electric", "water", "gas", "utility", "internet", "phone", "cable", "petron", "shell", "caltex", "meralco", "maynilad", "pldt",
                  "pldthome", "pldthomefibr", "smart", "globe", "mr diy"],
    "Transportation": ["taxi", "uber", "train", "bus", "flight", "airlines", "car rental", "fuel", "gas station",
                       "grab", "taxi receipt", "angkas", "moveit", "move it", "lrt", "mrt"],
    "Entertainment": ["movie", "concert", "theater", "game", "entertainment", "music"],
    "Healthcare": ["pharmacy", "hospital", "clinic", "dentist", "optician", "medical", "mercury drug", "mercury drugs"],
    "Clothes": ["uni qlo", "uniqlo", "bench", "penshoppe", "smstore", "medical"],
    "Miscellaneous": []
}

# Training Dataset for ML-Based Categorization
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
    if vendor.lower() in [v.lower() for v in RULE_BASED_CATEGORIES.keys()]:
        return RULE_BASED_CATEGORIES[vendor]

    combined_text = f"{vendor} {description}".lower()
    for category, keywords in RULE_BASED_CATEGORIES.items():
        if any(keyword in combined_text for keyword in keywords):
            return category

    return ml_categorize(combined_text, vectorizer, X, categories)

# Preprocess Image
def preprocess_image(image_path):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return thresh

# Perform OCR
def perform_ocr(image):
    return pytesseract.image_to_string(Image.fromarray(image))

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
    print("Receipt saved to MySQL database.")
    cursor.close()
    conn.close()

# Process Receipt Image
def process_receipt(image_path, vectorizer, X, categories):
    processed_image = preprocess_image(image_path)
    ocr_text = perform_ocr(processed_image)
    print("OCR Text Output:\n", ocr_text)

    receipt_data = extract_details(ocr_text)
    print("Extracted Receipt Data:", receipt_data)

    receipt_data["category"] = categorize_receipt(receipt_data["vendor"], ocr_text, vectorizer, X, categories)
    print("Categorized as:", receipt_data["category"])

    save_to_database(receipt_data)

# Main Function
def main():
    folder_path = 'C:/Users/CEO Ivo John Barroba/Downloads/dataset/receipts'
    vectorizer, X, categories = train_ml_model(TRAINING_DATA)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            image_path = os.path.join(folder_path, filename)
            print(f"\nProcessing: {filename}")
            process_receipt(image_path, vectorizer, X, categories)

if __name__ == "__main__":
    main()
