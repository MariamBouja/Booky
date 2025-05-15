from flask_bcrypt import Bcrypt
import psycopg2
from psycopg2 import sql
import config
from flask import Flask, request, session, redirect, url_for, jsonify
from datetime import date
from flask import render_template
from datetime import timedelta




app = Flask(__name__)
app.secret_key = config.SECRET_KEY

bcrypt = Bcrypt(app)

# Database connection function
def get_db_connection():
    conn = psycopg2.connect(
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASS,
        host=config.DB_HOST,
        port=config.DB_PORT
    )
    conn.autocommit = True
    return conn



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
    cur.execute("SELECT * FROM Book;")
    books = cur.fetchall()
    cur.close()
    conn.close()

    headers = ["ID", "Title", "Author_ID", "Year", "Genre", "Language", "Copies", "Condition"]
    return render_template("books.html", title="All Books", headers=headers, rows=books)







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
            cur.execute("""
                INSERT INTO "AppUser" (User_Fname, User_Lname, Phone, Email, Password, User_Is_Student)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (fname, lname, phone, email, hashed_password, True))

            conn.commit()
            return redirect(url_for("home"))

        except psycopg2.IntegrityError:
            conn.rollback()
            return "Email already exists", 400

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
        cur.execute("SELECT User_ID, Password FROM \"AppUser\" WHERE Email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and bcrypt.check_password_hash(user[1], password):
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

        cur.execute("SELECT COUNT(*) FROM Booking WHERE User_ID = %s AND Return_Date IS NULL", (user_id,))
        active_count = cur.fetchone()[0]
        if active_count >= 3:
            return "Booking limit reached", 403

        cur.execute("SELECT Available_Copies FROM Book WHERE Book_ID = %s", (book_id,))
        copies = cur.fetchone()[0]
        if copies <= 0:
            return "Book not available", 403

        cur.execute("""
            SELECT * FROM Booking
            WHERE User_ID = %s AND Book_ID = %s AND Return_Date IS NULL
        """, (user_id, book_id))
        if cur.fetchone():
            return "Already borrowed this book.", 403

        cur.execute("""
            INSERT INTO Booking (Booking_Date, Due_Date, User_ID, Book_ID)
            VALUES (%s, %s, %s, %s)
        """, (today, due, user_id, book_id))

        cur.execute("""
            UPDATE Book SET Available_Copies = Available_Copies - 1
            WHERE Book_ID = %s
        """, (book_id,))
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("list_books"))

    else:
        # GET request → show form
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT Book_ID, Book_Title FROM Book WHERE Available_Copies > 0")
        books = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("borrow.html", books=books)



    


    # GET request → Show form
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT Book_ID, Book_Title FROM Book WHERE Available_Copies > 0")
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("borrow.html", books=books)


if __name__ == "__main__":
    app.run(debug=True)
