from flask import Flask, jsonify
import io
import os
import sys
from crewai import Agent, Crew, LLM, Process, Task

app = Flask(__name__)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_KEY = os.environ.get("OPENAI_API_KEY", "sk-dmr3ZOwsSIaS12i7IrN3IIinTTdLbHoCbI0F92u3AiF0AV7u")

# 1. Server தொடங்கும் போதே Agent & Crew-ஐ உருவாக்குவதால் RAM Crash ஆகாது
my_llm = LLM(
    model="openai/moonshotai/kimi-k3-free",
    base_url="https://api.tokenrouter.com/v1",
    api_key=API_KEY,
    timeout=120 
)

accounting_agent = Agent(
    role="Loan Accounting Engine",
    goal="Provide Decimal calculation code for loans.",
    backstory="You are an NBFC accounting expert focusing on Python Decimal logic.",
    llm=my_llm
)

operations_agent = Agent(
    role="Field Collection Lead",
    goal="Define WhatsApp OTP collection API logic.",
    backstory="You design secure real-time OTP collection workflows.",
    llm=my_llm
)

compliance_agent = Agent(
    role="RBI Compliance Specialist",
    goal="Detail RBI Fair Practices Code logging.",
    backstory="You ensure MFI compliance and grievance routing.",
    llm=my_llm
)

task1 = Task(
    description="Write concise Python code using `decimal.Decimal` to calculate monthly EMI for a loan of ₹40,000 at 12% flat rate for 12 months.",
    expected_output="Short Python code snippet with Decimal calculations.",
    agent=accounting_agent
)

task2 = Task(
    description="Outline 4 key API steps for generating and verifying a 6-digit WhatsApp OTP during field collection.",
    expected_output="4 bullet points explaining the OTP workflow.",
    agent=operations_agent
)

task3 = Task(
    description="List 3 mandatory steps to log RBI Fair Practices Code disclosure before loan approval.",
    expected_output="3 bullet points covering compliance steps.",
    agent=compliance_agent
)

microfinance_crew = Crew(
    agents=[accounting_agent, operations_agent, compliance_agent],
    tasks=[task1, task2, task3],
    process=Process.sequential,
    verbose=True
)

# Render Health Check-க்கான Route
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Server is healthy"}), 200

# Main Endpoint
@app.route('/', methods=['GET'])
def run_crew():
    try:
        result = microfinance_crew.kickoff()
        return jsonify({
            "status": "success",
            "result": str(result)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)