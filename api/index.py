from flask import Flask, jsonify
import os
from openai import OpenAI

app = Flask(__name__)

API_KEY = os.environ.get("OPENAI_API_KEY", "sk-dmr3ZOwsSIaS12i7IrN3IIinTTdLbHoCbI0F92u3AiF0AV7u")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.tokenrouter.com/v1"
)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Server is healthy"}), 200

@app.route('/', methods=['GET'])
def run_agents():
    try:
        # Agent 1: Loan Accounting Engine
        task1 = client.chat.completions.create(
            model="openai/moonshotai/kimi-k3-free",
            messages=[
                {"role": "system", "content": "You are a Loan Accounting Engine and NBFC expert focusing on Python Decimal logic."},
                {"role": "user", "content": "Write concise Python code using `decimal.Decimal` to calculate monthly EMI for a loan of ₹40,000 at 12% flat rate for 12 months."}
            ]
        ).choices[0].message.content

        # Agent 2: Field Collection Lead
        task2 = client.chat.completions.create(
            model="openai/moonshotai/kimi-k3-free",
            messages=[
                {"role": "system", "content": "You are a Field Collection Lead who designs secure real-time OTP collection workflows."},
                {"role": "user", "content": "Outline 4 key API steps for generating and verifying a 6-digit WhatsApp OTP during field collection."}
            ]
        ).choices[0].message.content

        # Agent 3: RBI Compliance Specialist
        task3 = client.chat.completions.create(
            model="openai/moonshotai/kimi-k3-free",
            messages=[
                {"role": "system", "content": "You are an RBI Compliance Specialist ensuring MFI compliance and grievance routing."},
                {"role": "user", "content": "List 3 mandatory steps to log RBI Fair Practices Code disclosure before loan approval."}
            ]
        ).choices[0].message.content

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