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
        dbname="tracker_DB",
        user="postgres",
        password="postgres123",
        host="localhost",
        port="5432"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        conn.commit()
        cur.close()
        conn.close()
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

    cur.execute(
        "SELECT * FROM habits WHERE user_id = %s", (user_id,)
    )
    habits = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("index.html", habits=habits)

 
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
        cur.execute(
            "SELECT * FROM users WHERE username = %s", (username,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect("/")
    
    return render_template("login.html")

@app.route("/toggle/<int:id>")
def toggle(id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1️⃣ Read habit
    cur.execute(
        """
        SELECT streak, last_done
        FROM habits
        WHERE id = %s AND user_id = %s
        """,
        (id, session["user_id"])
    )
    habit = cur.fetchone()

    if not habit:
        cur.close()
        conn.close()
        return redirect("/")

    today = date.today()
    last_done = habit["last_done"]

    # 2️⃣ If already done today → no change
    if last_done == today:
        cur.close()
        conn.close()
        return redirect("/")

    # 3️⃣ Calculate new streak
    if last_done == today - timedelta(days=1):
        new_streak = habit["streak"] + 1
    else:
        new_streak = 1

    # 4️⃣ Update
    cur.execute(
        """
        UPDATE habits
        SET done = TRUE, streak = %s, last_done = %s
        WHERE id = %s AND user_id = %s
        """,
        (new_streak, today, id, session["user_id"])
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/")


@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("DELETE FROM habits WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")

@app.route("/stats")
def stats():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


    cur.execute(
        "SELECT COUNT(*) AS total FROM habits WHERE user_id = %s",
        (user_id,)
    )
    total_habits = cur.fetchone()["total"]

    today = date.today()

    cur.execute(
        "SELECT COUNT(*) AS completed FROM habits WHERE user_id = %s AND last_done = %s",
        (user_id, today)
    )
    completed_today = cur.fetchone()["completed"]

    cur.execute(
        "SELECT MAX(streak) AS best FROM habits WHERE user_id = %s",
        (user_id,)
    )
    best_streak = cur.fetchone()["best"]

    # Weekly data (last 7 days)
    days = []
    counts = []

    for i in range(6, -1, -1):
        day = (date.today() - timedelta(days=i))
        cur.execute(
            "SELECT COUNT(*) AS count FROM habits WHERE user_id = %s AND last_done = %s",
            (user_id, day)
        )
        count = cur.fetchone()['count']
        days.append(day)
        counts.append(count)

    cur.close()
    conn.close()

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
