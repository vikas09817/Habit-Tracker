from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import os 

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY","supersecretkey")


# Database connection helper
def get_db_connection():
    return psycopg2.connect(
        dbname= os.environ.get("DB_NAME"),
        user= os.environ.get("DB_USER"),
        password= os.environ.get("DB_PASSWORD"),
        host= os.environ.get("DB_HOST"),
        port= int(os.environ.get("DB_PORT", 5432))
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

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            if request.method == "POST":
                habit_name = request.form["habit"]
                category = request.form.get("category") or "General"
                color = request.form["color"]
                reminder_time = request.form.get("reminder_time") or None
                cur.execute(
                    "INSERT INTO habits (name, user_id, category, color, reminder_time) VALUES (%s, %s, %s, %s, %s)",
                    (habit_name, user_id, category, color, reminder_time)
                )
                conn.commit()
                return redirect("/")

            cur.execute(
                """
                SELECT h.id, h.name, h.category, h.color, h.streak,
                    (
                        SELECT MAX(hc.completed_on)
                        FROM habit_completions hc
                        WHERE hc.habit_id = h.id
                    ) AS last_done,
                    EXISTS (
                        SELECT 1 FROM habit_completions hc
                        WHERE hc.habit_id = h.id
                        AND hc.completed_on = CURRENT_DATE
                    ) AS done_today
                FROM habits h
                WHERE h.user_id = %s
                """,
                (user_id,)
            )
            habits = cur.fetchall()

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

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")


@app.route("/toggle/<int:id>")
def toggle(id):
    if "user_id" not in session:
        return redirect("/login")

    today = date.today()

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1️⃣ Verify the habit exists and belongs to the current user
            cur.execute(
                "SELECT id FROM habits WHERE id = %s AND user_id = %s AND is_deleted = FALSE",
                (id, session["user_id"])
            )
            if not cur.fetchone():
                return redirect("/")
            # 2️⃣ Check if today's completion already exists for this habit
            cur.execute(
                """
                SELECT 1 FROM habit_completions
                WHERE habit_id = %s AND completed_on = %s
                """,
                (id, today)
            )
            exists = cur.fetchone()

            # 3️⃣ Toggle logic
            if exists:
                # 🔄 UNTOGGLE: user clicked again → remove today's completion
                cur.execute(
                    "DELETE FROM habit_completions WHERE habit_id = %s AND completed_on = %s",
                    (id, today)
                )
            else:
                # ✅ TOGGLE ON: insert a completion record for today
                cur.execute(
                    "INSERT INTO habit_completions (habit_id, completed_on) VALUES (%s, %s)",
                    (id, today)
                )

            # 4️⃣ Recompute streak from completion history
            # We calculate streak dynamically to keep it accurate and recoverable
            cur.execute(
                """
                SELECT completed_on
                FROM habit_completions
                WHERE habit_id = %s
                ORDER BY completed_on DESC
                """,
                (id,)
            )

            dates = [r["completed_on"] for r in cur.fetchall()]

            # Count consecutive days starting from the most recent completion
            streak, prev = 0, None
            for d in dates:
                if prev is None:
                    # First (most recent) completion always starts the streak
                    streak = 1
                elif prev - timedelta(days=1) == d:
                    # Consecutive day → streak continues
                    streak += 1
                else:
                    # Gap found → streak ends
                    break
                prev = d

            cur.execute(
                "UPDATE habits SET streak = %s WHERE id = %s",
                (streak, id)
            )

            conn.commit()

    return redirect("/")

@app.route("/edit/<int:id>", methods=["POST"])
def edit(id):
    if "user_id" not in session:
        return redirect("/login")

    name = request.form["name"]
    category = request.form["category"]
    color = request.form["color"]

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            cur.execute(
                """
                UPDATE habits
                SET name = %s, category = %s, color = %s
                WHERE id = %s AND user_id = %s AND is_deleted = FALSE
                """,
                (name, category, color, id, session["user_id"])
            )

    conn.commit()

    conn.close()

    return redirect("/")


@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("UPDATE habits SET is_deleted = TRUE WHERE id = %s AND user_id = %s", (id, session["user_id"]))
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
        """
        SELECT COUNT(*) AS completed
        FROM habit_completions hc
        JOIN habits h ON h.id = hc.habit_id
        WHERE h.user_id = %s AND hc.completed_on = CURRENT_DATE
        """,
        (user_id,)
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
            """
            SELECT COUNT(*) AS count
            FROM habit_completions hc
            JOIN habits h ON h.id = hc.habit_id
            WHERE h.user_id = %s AND hc.completed_on = %s
            """,
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
