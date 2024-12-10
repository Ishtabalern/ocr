from flask import Flask, jsonify, request
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)  # Allow all origins by default

@app.route('/run-script', methods=['POST'])
def run_script():
    try:
        result = subprocess.run(['python', 'teseract.py'], check=True, capture_output=True, text=True)
        return jsonify({'success': True, 'output': result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'error': str(e), 'output': e.output}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
