from pathlib import Path
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os
import time

base_dir = Path(__file__).resolve().parent
templates_dir = base_dir / "templates"
data_mappe = base_dir / "vibyfysio" / "data"

print("Kører app fra fil:", __file__)
print("Current working directory:", os.getcwd())
print("Templates-mappe:", templates_dir)
print("Data-mappe:", data_mappe)

app = Flask(__name__, template_folder=str(templates_dir))
client = OpenAI()

tekster = []

for fil in sorted(data_mappe.rglob("*.txt")):
    indhold = fil.read_text(encoding="utf-8")
    tekster.append(f"\n--- FIL: {fil.name} ---\n{indhold}")

virksomhedsinfo = "\n".join(tekster)

print("Antal tekstfiler fundet:", len(tekster))
print("Antal tegn i virksomhedsinfo:", len(virksomhedsinfo))

system_prompt = f"""
Du er chatbot for Viby Fysioterapi.

Du svarer kun på vegne af Viby Fysioterapi og må kun bruge informationen nedenfor.

Regler:
- Du må ikke opfinde konkrete behandlinger, priser, åbningstider eller kontaktoplysninger.
- Du må ikke svare generelt på ting, der ikke handler om Viby Fysioterapi.
- Hold svarene korte, klare og hjælpsomme, helst 2-5 sætninger.
- Hvis brugeren spørger om booking eller kontakt, så brug kun de oplysninger, der findes i informationen.
- Hvis brugerens besked er uklar, meget kort eller uformel, så prøv først at forstå intentionen bag beskeden.
- Hvis der er en mulig relevant fortolkning, så hjælp brugeren videre forsigtigt.
- Hvis du er usikker, så stil et kort opklarende spørgsmål i stedet for bare at afvise.
- Hvis spørgsmålet er helt irrelevant for klinikken, så sig høfligt at du kun kan hjælpe med spørgsmål om Viby Fysioterapi, behandlinger, priser, kontakt og booking.
- Du må ikke opføre dig som en generel assistent eller skrive digte, kode, skolehjælp osv.
- Du må ikke stille diagnoser. Ved alvorlige eller akutte symptomer skal du anbefale at kontakte læge eller akut hjælp.
- Brug kun sætningen "Det kan jeg ikke se ud fra den information, jeg har fået." hvis der virkelig ikke er nogen rimelig kobling til informationen.

Her er informationen om Viby Fysioterapi:
{virksomhedsinfo}
"""

MAX_MESSAGE_LENGTH = 400
MAX_HISTORY_ITEMS = 8
MIN_SECONDS_BETWEEN_MESSAGES = 2.5

last_request_by_ip = {}


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    ip = get_client_ip()
    now = time.time()

    last_time = last_request_by_ip.get(ip)
    if last_time and (now - last_time) < MIN_SECONDS_BETWEEN_MESSAGES:
        wait_seconds = round(MIN_SECONDS_BETWEEN_MESSAGES - (now - last_time), 1)
        return jsonify({
            "error": f"Vent lige {wait_seconds} sekunder før du sender igen."
        }), 429

    data = request.get_json()

    if not data:
        return jsonify({"error": "Ingen data modtaget."}), 400

    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Tom besked."}), 400

    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({
            "error": f"Din besked er for lang. Hold den under {MAX_MESSAGE_LENGTH} tegn."
        }), 400

    if not isinstance(history, list):
        history = []

    trimmed_history = history[-MAX_HISTORY_ITEMS:]

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    for item in trimmed_history:
        role = item.get("role")
        content = item.get("content", "").strip()

        if role in ["user", "assistant"] and content:
            messages.append({"role": role, "content": content[:1000]})

    messages.append({"role": "user", "content": message})

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=messages
        )

        answer = response.output_text.strip()
        last_request_by_ip[ip] = now

        return jsonify({"answer": answer})

    except Exception:
        return jsonify({
            "error": "Der opstod en fejl. Prøv igen om lidt."
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
