from flask import Flask, jsonify
import io
import os
import sys
import threading
from crewai import Agent, Crew, LLM, Process, Task

app = Flask(__name__)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_KEY = os.environ.get("OPENAI_API_KEY", "sk-dmr3ZOwsSIaS12i7IrN3IIinTTdLbHoCbI0F92u3AiF0AV7u")

# பின்னணி செயல்பாட்டைக் கண்காணிக்க Global Variable
execution_status = {
    "is_running": False,
    "result": None,
    "error": None
}

def run_crew_in_background():
    global execution_status
    execution_status["is_running"] = True
    execution_status["error"] = None
    
    try:
        my_llm = LLM(
            model="openai/moonshotai/kimi-k3-free",
            base_url="https://api.tokenrouter.com/v1",
            api_key=API_KEY,
            timeout=120
        )

        accounting_agent = Agent(
            role="Loan Accounting Engine",
            goal="Provide Decimal calculation code for loans.",
            backstory="You are an NBFC accounting expert.",
            llm=my_llm,
            verbose=False
        )

        operations_agent = Agent(
            role="Field Collection Lead",
            goal="Define WhatsApp OTP collection API logic.",
            backstory="You design secure real-time OTP collection workflows.",
            llm=my_llm,
            verbose=False
        )

        compliance_agent = Agent(
            role="RBI Compliance Specialist",
            goal="Detail RBI Fair Practices Code logging.",
            backstory="You ensure MFI compliance.",
            llm=my_llm,
            verbose=False
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
            verbose=False
        )

        output = microfinance_crew.kickoff()
        execution_status["result"] = str(output)
    except Exception as e:
        execution_status["error"] = str(e)
    finally:
        execution_status["is_running"] = False

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Server is healthy"}), 200

@app.route('/', methods=['GET'])
def index():
    global execution_status
    
    # 1. விடை ஏற்கனவே தயாராக இருந்தால் அதை உடனே காட்டவும்
    if execution_status["result"]:
        return jsonify({
            "status": "completed",
            "result": execution_status["result"]
        })
    
    # 2. ஏதேனும் எரர் வந்தால் அதைக் காட்டவும்
    if execution_status["error"]:
        return jsonify({
            "status": "error",
            "message": execution_status["error"]
        }), 500

    # 3. ஏற்கனவே பின்னணியில் இயங்கிக் கொண்டிருந்தால் காத்திருக்கச் சொல்லவும்
    if execution_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "CrewAI is processing in background. Please refresh this page after 30 seconds."
        }), 202

    # 4. முதல்முறை அழைக்கும்போது Background Thread-ஐ தொடங்கவும் (இது 0.1 நொடியில் பதில் அளித்துவிடும், அதனால் 502 வராது)
    thread = threading.Thread(target=run_crew_in_background)
    thread.start()
    
    return jsonify({
        "status": "started",
        "message": "CrewAI process has started! Please refresh this page in 30-40 seconds to view output."
    }), 202

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)