from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
import pdfplumber
import re
import sqlite3
import tempfile

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

CORRECT_MARK = 2
WRONG_MARK = -0.5

# Load answer key
answer_df = pd.read_csv("answer_key.csv")
answer_key = dict(zip(answer_df["QuestionID"].astype(str),
                      answer_df["Answer"].astype(str)))

# Database
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS results(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
mobile TEXT,
score REAL,
accuracy REAL
)
""")

conn.commit()


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/evaluate")
async def evaluate(request: Request,
                   name: str = Form(...),
                   mobile: str = Form(...),
                   file: UploadFile = File(...)):

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(await file.read())
        pdf_path = tmp.name

    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()

    pattern = r"Question ID\s*:\s*(\d+).*?Chosen Option\s*:\s*(\d+|--)"
    matches = re.findall(pattern, text, re.S)

    responses = {}
    for qid, opt in matches:
        responses[qid] = opt

    correct = 0
    wrong = 0
    unattempted = 0
    score = 0

    for qid, correct_ans in answer_key.items():

        response = responses.get(qid, "--")

        if response == "--":
            unattempted += 1

        elif response == correct_ans:
            correct += 1
            score += CORRECT_MARK

        else:
            wrong += 1
            score += WRONG_MARK

    attempted = correct + wrong
    accuracy = (correct / attempted * 100) if attempted > 0 else 0

    # Save to database
    cursor.execute(
        "INSERT INTO results(name,mobile,score,accuracy) VALUES (?,?,?,?)",
        (name, mobile, score, round(accuracy, 2))
    )
    conn.commit()

    # Create Excel
    df = pd.DataFrame([{
        "Name": name,
        "Mobile": mobile,
        "Correct": correct,
        "Wrong": wrong,
        "Unattempted": unattempted,
        "Score": score,
        "Accuracy": round(accuracy,2)
    }])

    df.to_excel("static/result.xlsx", index=False)

    result = {
        "name": name,
        "mobile": mobile,
        "correct": correct,
        "wrong": wrong,
        "unattempted": unattempted,
        "score": score,
        "accuracy": round(accuracy,2)
    }

    return templates.TemplateResponse("result.html",
                                      {"request": request,
                                       "result": result})


@app.get("/leaderboard")
def leaderboard(request: Request):

    cursor.execute("SELECT name,score,accuracy FROM results ORDER BY score DESC LIMIT 20")

    rows = cursor.fetchall()

    return templates.TemplateResponse("leaderboard.html",
                                      {"request": request,
                                       "rows": rows})
