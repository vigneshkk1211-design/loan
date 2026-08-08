import io
import os
import sys

from flask import Flask, jsonify
from crewai import Agent, Crew, LLM, Process, Task

# ---------------------------------------------------------------------------
# Encoding fix – ensures UTF-8 output even inside Vercel's sandboxed runtime
# ---------------------------------------------------------------------------
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ---------------------------------------------------------------------------
# API key – prefer the environment variable injected via Vercel's dashboard;
# fall back to the hard-coded key only when the env-var is absent.
# ---------------------------------------------------------------------------
API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "sk-dmr3ZOwsSIaS12i7IrN3IIinTTdLbHoCbI0F92u3AiF0AV7u",
)
os.environ["OPENAI_API_KEY"] = API_KEY

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------
app = Flask(__name__)


def build_crew() -> Crew:
    """
    Instantiate and return a fresh Crew on every request.
    Agents and Tasks are lightweight objects, so recreating them per-request
    is the safest approach inside a stateless serverless environment.
    """
    my_llm = LLM(
        model="openai/moonshotai/kimi-k3-free",
        base_url="https://api.tokenrouter.com/v1",
        api_key=API_KEY,
        timeout=120,
    )

    # --- Agents ---
    accounting_agent = Agent(
        role="Loan Accounting Engine",
        goal="Provide Decimal calculation code for loans.",
        backstory="You are an NBFC accounting expert focusing on Python Decimal logic.",
        llm=my_llm,
    )

    operations_agent = Agent(
        role="Field Collection Lead",
        goal="Define WhatsApp OTP collection API logic.",
        backstory="You design secure real-time OTP collection workflows.",
        llm=my_llm,
    )

    compliance_agent = Agent(
        role="RBI Compliance Specialist",
        goal="Detail RBI Fair Practices Code logging.",
        backstory="You ensure MFI compliance and grievance routing.",
        llm=my_llm,
    )

    # --- Tasks ---
    task1 = Task(
        description=(
            "Write concise Python code using `decimal.Decimal` to calculate "
            "monthly EMI for a loan of Rs.40,000 at 12% flat rate for 12 months."
        ),
        expected_output="Short Python code snippet with Decimal calculations.",
        agent=accounting_agent,
    )

    task2 = Task(
        description=(
            "Outline 4 key API steps for generating and verifying a 6-digit "
            "WhatsApp OTP during field collection."
        ),
        expected_output="4 bullet points explaining the OTP workflow.",
        agent=operations_agent,
    )

    task3 = Task(
        description=(
            "List 3 mandatory steps to log RBI Fair Practices Code disclosure "
            "before loan approval."
        ),
        expected_output="3 bullet points covering compliance steps.",
        agent=compliance_agent,
    )

    return Crew(
        agents=[accounting_agent, operations_agent, compliance_agent],
        tasks=[task1, task2, task3],
        process=Process.sequential,
        verbose=False,          # keep logs minimal inside serverless
    )


def run_crew() -> str:
    """Execute the crew and return a plain-text result string."""
    crew = build_crew()
    result = crew.kickoff()
    # CrewAI may return a CrewOutput object or a plain string depending on version
    return str(result)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
@app.route("/api", methods=["GET"])
def handle_request():
    """
    Main serverless handler.

    Returns
    -------
    JSON  {"status": "success", "result": <crew output>}
          {"status": "error",   "message": <error description>}
    """
    try:
        output = run_crew()
        return jsonify({"status": "success", "result": output}), 200

    except ValueError as exc:
        return jsonify({"status": "error", "message": f"Value error: {exc}"}), 422

    except RuntimeError as exc:
        return jsonify({"status": "error", "message": f"Runtime error: {exc}"}), 500

    except Exception as exc:  # noqa: BLE001  – catch-all for unexpected errors
        return (
            jsonify({"status": "error", "message": f"Unexpected error: {exc}"}),
            500,
        )


# ---------------------------------------------------------------------------
# Local development entry-point (not invoked by Vercel)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
