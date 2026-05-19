import os
import json
from flask import Flask, render_template, request, jsonify
from PyPDF2 import PdfReader
import google.generativeai as genai
from dotenv import load_dotenv

# Load API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=api_key)

app = Flask(__name__)

def get_available_model():
    """Automatically finds a working model for your API key."""
    try:
        # List all models available to your specific key
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # Priority list: Try to find the best available model
        preferred_order = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-flash-001',
            'models/gemini-1.5-flash-002',
            'models/gemini-pro',
            'models/gemini-1.0-pro'
        ]
        
        for model in preferred_order:
            if model in available_models:
                print(f"✅ Using model: {model}")
                return model
        
        # If none of the preferred ones exist, take the first available one
        if available_models:
            print(f"⚠️ Preferred models not found. Using fallback: {available_models[0]}")
            return available_models[0]
            
    except Exception as e:
        print(f"Error listing models: {e}")
    
    # Absolute fallback
    return 'models/gemini-1.5-flash'

# Set the model once at startup
ACTIVE_MODEL_NAME = get_available_model()

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # 1. Get Data
        job_description = request.form.get('jd')
        resume_file = request.files.get('resume')

        if not job_description or not resume_file:
            return jsonify({"error": "Missing JD or Resume file"}), 400

        # 2. Extract PDF Text
        resume_text = extract_text_from_pdf(resume_file)

        # 3. Create the Prompt
        prompt = f"""
        Act as an expert ATS (Application Tracking System).
        Compare the following Resume against the Job Description.

        JOB DESCRIPTION:
        {job_description}

        RESUME:
        {resume_text}

        OUTPUT INSTRUCTION:
        You must output ONLY valid JSON. Do not include markdown formatting like ```json. 
        Follow this exact schema:
        {{
            "match_percentage": (integer between 0 and 100),
            "missing_keywords": ["keyword1", "keyword2", "keyword3"],
            "strengths": ["strength1", "strength2", "strength3"],
            "weaknesses": ["weakness1", "weakness2", "weakness3"],
            "final_verdict": "A concise 2 sentence summary."
        }}
        """

        # 4. Call Gemini API using the auto-detected model
        model = genai.GenerativeModel(ACTIVE_MODEL_NAME)
        response = model.generate_content(prompt)
        
        # 5. Clean and Parse Response
        ai_text = response.text
        
        # Clean up markdown if present
        if "```" in ai_text:
            ai_text = ai_text.replace("```json", "").replace("```", "").strip()
        
        result_json = json.loads(ai_text)
        return jsonify(result_json)

    except Exception as e:
        print(f"SERVER ERROR: {e}")
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

if __name__ == '__main__':
    print("Starting Flask Server...")
    app.run(debug=True)