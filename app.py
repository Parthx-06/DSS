import os
from flask import Flask, render_template, request
from dotenv import load_dotenv
from pypdf import PdfReader
from google import genai
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


load_dotenv()

app = Flask(__name__)

# Gemini setup
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""

    for page in reader.pages:
        text += page.extract_text()

    return text


@app.route("/", methods=["GET", "POST"])
def index():

    summary = None

    if request.method == "POST":

        file = request.files["pdf"]

        if file:

            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)

            pdf_text = extract_text_from_pdf(filepath)

            prompt = f"""
            You are a data analyst.

            Analyze the following CSV dataset and provide:

            1. Summary of dataset
            2. Key insights
            3. Patterns or trends
            4. Suggestions for improvement

            give in the pointwise upto 10 points or more

            Dataset:
            {pdf_text}
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            summary = response.text 

            
    return render_template("index.html", summary=summary)


@app.route("/dashboard.html")
def dashboard():
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(debug=True)