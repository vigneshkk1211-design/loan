from flask import Flask, jsonify
import os
from openai import OpenAI

app = Flask(__name__)

API_KEY = os.environ.get("OPENAI_API_KEY", "sk-dmr3ZOwsSIaS12i7IrN3IIinTTdLbHoCbI0F92u3AiF0AV7u")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.tokenrouter.com/v1"
)

# TokenRouter-இல் அணுகக்கூடிய சாத்தியமான மாடல்களின் பட்டியல்
CANDIDATE_MODELS = [
    "openai/gpt-3.5-turbo",
    "gpt-3.5-turbo",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct",
    "openai/moonshotai/kimi-k3-free"
]

def generate_completion(system_prompt, user_prompt):
    """ஒரு மாடலில் 403 எரர் வந்தால் தானாக அடுத்த மாடலை முயற்சி செய்யும் ஃபங்க்ஷன்"""
    last_error = None
    for model in CANDIDATE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = str(e)
            continue
    raise Exception(f"All models failed. Last error: {last_error}")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Server is healthy"}), 200

@app.route('/', methods=['GET'])
@app.route('/api', methods=['GET'])
def run_agents():
    try:
        # Task 1: Loan Accounting Engine
        task1 = generate_completion(
            system_prompt="You are a Loan Accounting Engine and NBFC expert focusing on Python Decimal logic.",
            user_prompt="Write concise Python code using `decimal.Decimal` to calculate monthly EMI for a loan of ₹40,000 at 12% flat rate for 12 months."
        )

        # Task 2: Field Collection Lead
        task2 = generate_completion(
            system_prompt="You are a Field Collection Lead who designs secure real-time OTP collection workflows.",
            user_prompt="Outline 4 key API steps for generating and verifying a 6-digit WhatsApp OTP during field collection."
        )

        # Task 3: RBI Compliance Specialist
        task3 = generate_completion(
            system_prompt="You are an RBI Compliance Specialist ensuring MFI compliance and grievance routing.",
            user_prompt="List 3 mandatory steps to log RBI Fair Practices Code disclosure before loan approval."
        )

        full_result = f"=== TASK 1: EMI CALCULATION ===\n{task1}\n\n=== TASK 2: WHATSAPP OTP WORKFLOW ===\n{task2}\n\n=== TASK 3: RBI COMPLIANCE LOGGING ===\n{task3}"

        return jsonify({
            "status": "success",
            "result": full_result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)