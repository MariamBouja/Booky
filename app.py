from flask_bcrypt import Bcrypt
from flask import flash
import psycopg2
from flask import Flask, request, session, redirect, url_for, jsonify, render_template
from datetime import date, timedelta, datetime
from decimal import Decimal
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

bcrypt = Bcrypt(app)

def get_db_connection():
    return psycopg2.connect(
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASS,
        host=config.DB_HOST,
        port=config.DB_PORT
    )

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/test-db")
def test_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT version();")
    result = cur.fetchone()
    cur.close()
    conn.close()
    return f"Database connected: {result[0]}"

@app.route("/books")
def list_books():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM book WHERE available_copies > 0;")
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("books.html", books=books)



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fname = request.form["first_name"]
        lname = request.form["last_name"]
        phone = request.form["phone"]
        email = request.form["email"]
        password = request.form["password"]
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("SELECT 1 FROM Appuser WHERE email = %s", (email,))
            if cur.fetchone():
                return "Email already registered.", 400

            cur.execute("SELECT COALESCE(MAX(user_id), 100) + 1 FROM Appuser")
            new_user_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO Appuser (user_id, user_fname, user_lname, phone, email, password, user_is_student)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (new_user_id, fname, lname, phone, email, hashed_password, True))

            conn.commit()
            return redirect(url_for("home"))

        except psycopg2.IntegrityError as e:
            conn.rollback()
            return "Signup error: " + str(e), 400

        finally:
            cur.close()
            conn.close()

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, password FROM Appuser WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        # ✅ Add check for NULL password
        if user and user[1] and bcrypt.check_password_hash(user[1], password):
            session["user_id"] = user[0]
            return redirect(url_for("home"))
        else:
            return "Invalid credentials", 401

    return render_template("login.html")



@app.route("/borrow", methods=["GET", "POST"])
def borrow():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        book_id = request.form["book_id"]
        today = date.today()
        due = today + timedelta(days=30)

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # Check limit
            cur.execute("SELECT COUNT(*) FROM booking WHERE user_id = %s AND return_date IS NULL", (user_id,))
            if cur.fetchone()[0] >= 3:
                flash("You reached the limit of 3 active borrowed books.", "error")
                return redirect(url_for("borrow"))

            # Check book availability
            cur.execute("SELECT available_copies FROM book WHERE book_id = %s", (book_id,))
            copies = cur.fetchone()
            if not copies or int(copies[0]) <= 0:
                flash("This book is no longer available.", "error")
                return redirect(url_for("borrow"))

            # Already borrowed?
            cur.execute("SELECT 1 FROM booking WHERE user_id = %s AND book_id = %s AND return_date IS NULL", (user_id, book_id))
            if cur.fetchone():
                flash("You already borrowed this book.", "warning")
                return redirect(url_for("borrow"))

            # Borrow the book
            cur.execute("""
                INSERT INTO booking (booking_date, due_date, user_id, book_id)
                VALUES (%s, %s, %s, %s)
            """, (today, due, user_id, book_id))

            cur.execute("""
                UPDATE book SET available_copies = available_copies - 1
                WHERE book_id = %s
            """, (book_id,))

            conn.commit()
            flash("Book borrowed successfully!", "success")
            return redirect(url_for("my_books"))

        finally:
            cur.close()
            conn.close()

    # GET request: show books
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT book_id, book_title FROM book WHERE available_copies > 0")
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("borrow.html", books=books)


@app.route("/my-books")
def my_books():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT b.booking_id, bk.book_title, b.booking_date, b.due_date, bk.book_id
        FROM booking b
        JOIN book bk ON b.book_id = bk.book_id
        WHERE b.user_id = %s AND b.return_date IS NULL
        ORDER BY b.due_date ASC
    """, (user_id,))
    active_bookings = cur.fetchall()

    cur.execute("""
        SELECT b.booking_id, bk.book_title, b.booking_date, b.due_date, b.return_date
        FROM booking b
        JOIN book bk ON b.book_id = bk.book_id
        WHERE b.user_id = %s AND b.return_date IS NOT NULL
        ORDER BY b.return_date DESC
    """, (user_id,))
    past_bookings = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("my_books.html", active_bookings=active_bookings, past_bookings=past_bookings)

@app.route("/return-book/<int:booking_id>", methods=["POST"])
def return_book(booking_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = date.today()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT book_id, due_date
        FROM booking
        WHERE booking_id = %s AND user_id = %s AND return_date IS NULL
    """, (booking_id, user_id))
    booking = cur.fetchone()
    if not booking:
        cur.close()
        conn.close()
        return "Invalid booking", 403

    book_id, due_date = booking

    cur.execute("UPDATE booking SET return_date = %s WHERE booking_id = %s", (today, booking_id))
    cur.execute("UPDATE book SET available_copies = available_copies + 1 WHERE book_id = %s", (book_id,))

    if today > due_date:
        days_late = (today - due_date).days
        late_fee = Decimal(days_late * 0.50)
        cur.execute("""
            INSERT INTO penalty (late_fee, date_issued, date_returned, booking_id)
            VALUES (%s, %s, %s, %s)
        """, (late_fee, today, today, booking_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("my_books"))

@app.route("/penalties")
def view_penalties():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.penaltyid, p.late_fee, p.date_issued, p.date_returned, 
               p.payment_date, b.booking_id, bk.book_title
        FROM penalty p
        JOIN booking b ON p.booking_id = b.booking_id
        JOIN book bk ON b.book_id = bk.book_id
        WHERE b.user_id = %s
        ORDER BY p.date_issued DESC
    """, (user_id,))
    penalties = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("penalties.html", penalties=penalties)

@app.route("/pay-penalty/<int:penalty_id>", methods=["POST"])
def pay_penalty(penalty_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = date.today()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.penaltyid
        FROM penalty p
        JOIN booking b ON p.booking_id = b.booking_id
        WHERE p.penaltyid = %s AND b.user_id = %s AND p.payment_date IS NULL
    """, (penalty_id, user_id))

    if not cur.fetchone():
        cur.close()
        conn.close()
        return "Invalid penalty", 403

    cur.execute("UPDATE penalty SET payment_date = %s WHERE penaltyid = %s", (today, penalty_id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("view_penalties"))

if __name__ == "__main__":
    app.run(debug=True)
