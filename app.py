from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
import psycopg2
import psycopg2.extras
import os 

app = Flask(__name__)
app.secret_key = "supersecretkey"


# Database connection helper
def get_db_connection():
    return psycopg2.connect(
        dbname="habit_tracker",
        user="postgres",
        password="your_password",
        host="localhost",
        port="5432"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        conn = get_db_connection()(cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        conn.commit()
        return redirect("/login")

    return render_template("register.html")


@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if request.method == "POST":
        habit_name = request.form["habit"]
        cur.execute(
            "INSERT INTO habits (name, user_id) VALUES (%s, %s)",
            (habit_name, user_id)
        )
        conn.commit()
        return redirect("/")

    habits = conn.execute(
        "SELECT * FROM habits WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()

    return render_template("index.html", habits=habits)

 
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect("/")
    
    return render_template("login.html")


@app.route("/toggle/<int:id>")
def toggle(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    habit = conn.execute(
        "SELECT done, streak, last_done FROM habits WHERE id = ?",
        (id,)
    ).fetchone()

    today = date.today()

    if habit["last_done"]:
        last_done = date.fromisoformat(habit["last_done"])
    else:
        last_done = None

    # If already marked today, do nothing
    if last_done == today:
        conn.close()
        return redirect("/")

    # Update streak logic
    if last_done == today - timedelta(days=1):
        new_streak = habit["streak"] + 1
    else:
        new_streak = 1

    conn.execute(
        "UPDATE habits SET done = 1, streak = ?, last_done = ? WHERE id = ?",
        (new_streak, today.isoformat(), id)
    )
    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM habits WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/stats")
def stats():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db_connection()

    total_habits = conn.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ?",
        (user_id,)
    ).fetchone()[0]

    today = date.today().isoformat()

    completed_today = conn.execute(
        "SELECT COUNT(*) FROM habits WHERE user_id = ? AND last_done = ?",
        (user_id, today)
    ).fetchone()[0]

    best_streak = conn.execute(
        "SELECT MAX(streak) FROM habits WHERE user_id = ?",
        (user_id,)
    ).fetchone()[0] or 0

    # Weekly data (last 7 days)
    days = []
    counts = []

    for i in range(6, -1, -1):
        day = (date.today() - timedelta(days=i)).isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM habits WHERE user_id = ? AND last_done = ?",
            (user_id, day)
        ).fetchone()[0]
        days.append(day)
        counts.append(count)

    conn.close()

    if days is None:
        days = []
    if counts is None:
        counts = []
    

    return render_template(
        "stats.html",
        total=total_habits,
        completed_today=completed_today,
        best_streak=best_streak,
        days=days,
        counts=counts
    )



if __name__ == "__main__":
    app.run()
