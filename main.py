
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
from threading import RLock
import re

app = FastAPI(title="Student Academic History API")

students = {}
lock = RLock()


class HistoryCourse(BaseModel):
    course_code: str
    term: str
    credits_earned: int
    status: str


class HistoryRequest(BaseModel):
    history: list[HistoryCourse]


class PlanCourse(BaseModel):
    course_code: str
    term: str


class PlanRequest(BaseModel):
    planned_courses: list[PlanCourse]


def parse_credits(value):
    try:
        number = float(value.strip())
        if number.is_integer():
            return int(number)
    except (ValueError, OverflowError):
        pass
    return 0


def grade_rank(value):
    value = value.strip().upper()

    if re.fullmatch(r"\d+(\.\d+)?%?", value):
        return 2

    if value in {"", "P", "PASS", "-", "—"}:
        return 0

    return 1


def parse_transcript(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        if not rows:
            continue

        header_index = None
        columns = None

        for index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            labels = [
                cell.get_text(" ", strip=True).lower()
                for cell in cells
            ]

            required = ["status", "course", "grade", "term", "credits"]

            if all(label in labels for label in required):
                columns = {
                    name: labels.index(name)
                    for name in required
                }
                header_index = index
                break

        if columns is None:
            continue

        for row in rows[header_index + 1:]:
            cells = row.find_all(["td", "th"], recursive=False)

            if len(cells) <= max(columns.values()):
                continue

            def cell(name):
                return cells[columns[name]].get_text(" ", strip=True)

            status = cell("status")
            course_code = cell("course")
            grade = cell("grade")
            term = cell("term")
            credits = parse_credits(cell("credits"))

            if status not in {"Completed", "In-Progress", "Attempted"}:
                continue

            if not term or not course_code:
                continue

            record = {
                "course_code": course_code,
                "term": term,
                "credits_earned": credits,
                "status": status,
            }

            key = (course_code, term)
            priority = (grade_rank(grade), credits)

            if key not in found or priority > found[key][0]:
                found[key] = (priority, record)

    return [entry[1] for entry in found.values()]


def get_student(student_id):
    if student_id not in students:
        raise HTTPException(
            status_code=404,
            detail="Student not found"
        )
    return students[student_id]


@app.get("/")
def home():
    return {"message": "Student Academic History API is running"}


@app.post("/api/v1/students/{student_id}/history/import", status_code=201)
async def import_history(student_id: str, file: UploadFile = File(...)):
    content = await file.read()
    history = parse_transcript(
        content.decode("utf-8-sig", errors="replace")
    )

    with lock:
        if student_id not in students:
            students[student_id] = {"history": [], "plan": []}

        students[student_id]["history"] = history

    return {
        "status": "success",
        "past_courses_imported": len(history)
    }


@app.put("/api/v1/students/{student_id}/history")
def update_history(student_id: str, body: HistoryRequest):
    with lock:
        student = get_student(student_id)
        student["history"] = [
            course.model_dump() for course in body.history
        ]

    return {
        "status": "success",
        "message": "Academic history updated successfully"
    }


@app.delete("/api/v1/students/{student_id}/history")
def delete_history(student_id: str):
    with lock:
        student = get_student(student_id)
        student["history"] = []

    return {"status": "success"}


@app.post("/api/v1/students/{student_id}/plan")
def create_plan(student_id: str, body: PlanRequest):
    with lock:
        student = get_student(student_id)
        student["plan"] = [
            course.model_dump() for course in body.planned_courses
        ]

    return {
        "status": "success",
        "planned_courses_saved": len(body.planned_courses)
    }


@app.put("/api/v1/students/{student_id}/plan")
def update_plan(student_id: str, body: PlanRequest):
    with lock:
        student = get_student(student_id)
        student["plan"] = [
            course.model_dump() for course in body.planned_courses
        ]

    return {
        "status": "success",
        "planned_courses_saved": len(body.planned_courses)
    }


@app.delete("/api/v1/students/{student_id}/plan")
def delete_plan(student_id: str):
    with lock:
        student = get_student(student_id)
        student["plan"] = []

    return {"status": "success"}


@app.get("/api/v1/students/{student_id}/profile")
def get_profile(student_id: str):
    with lock:
        student = get_student(student_id)

        return {
            "student_id": student_id,
            "history": [
                course.copy() for course in student["history"]
            ],
            "plan": [
                course.copy() for course in student["plan"]
            ]
        }
