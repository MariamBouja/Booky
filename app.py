from flask_bcrypt import Bcrypt
import psycopg2
from psycopg2 import sql
import config
from flask import Flask, request, session, redirect, url_for, jsonify
from datetime import date
from flask import render_template
from datetime import timedelta
from decimal import Decimal
from datetime import datetime





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
            # Check if email already exists
            cur.execute("SELECT 1 FROM \"AppUser\" WHERE Email = %s", (email,))
            if cur.fetchone():
                return "Email already registered.", 400

            # ✅ Generate new User_ID
            cur.execute("SELECT COALESCE(MAX(User_ID), 100) + 1 FROM \"AppUser\"")
            new_user_id = cur.fetchone()[0]

            # ✅ Insert with generated ID
            cur.execute("""
                INSERT INTO "AppUser" (User_ID, User_Fname, User_Lname, Phone, Email, Password, User_Is_Student)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (new_user_id, fname, lname, phone, email, hashed_password, True))

            conn.commit()
            return redirect(url_for("home"))

        except psycopg2.IntegrityError as e:
            conn.rollback()
            print("Signup error:", e)
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

# Add this route to app.py
@app.route("/my-books", methods=["GET"])
def my_books():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all active bookings for the user with book details
    cur.execute("""
        SELECT b.Booking_ID, bk.Book_Title, b.Booking_Date, b.Due_Date, bk.Book_ID
        FROM Booking b
        JOIN Book bk ON b.Book_ID = bk.Book_ID
        WHERE b.User_ID = %s AND b.Return_Date IS NULL
        ORDER BY b.Due_Date ASC
    """, (user_id,))
    
    active_bookings = cur.fetchall()
    
    # Get past bookings (returned books)
    cur.execute("""
        SELECT b.Booking_ID, bk.Book_Title, b.Booking_Date, b.Due_Date, b.Return_Date
        FROM Booking b
        JOIN Book bk ON b.Book_ID = bk.Book_ID
        WHERE b.User_ID = %s AND b.Return_Date IS NOT NULL
        ORDER BY b.Return_Date DESC
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
    
    # Verify the booking belongs to the user
    cur.execute("""
        SELECT b.Book_ID, b.Due_Date
        FROM Booking b
        WHERE b.Booking_ID = %s AND b.User_ID = %s AND b.Return_Date IS NULL
    """, (booking_id, user_id))
    
    booking = cur.fetchone()
    if not booking:
        cur.close()
        conn.close()
        return "Invalid booking", 403
    
    book_id, due_date = booking
    
    # Update the booking with return date
    cur.execute("""
        UPDATE Booking
        SET Return_Date = %s
        WHERE Booking_ID = %s
    """, (today, booking_id))
    
    # Increase available copies of the book
    cur.execute("""
        UPDATE Book
        SET Available_Copies = Available_Copies + 1
        WHERE Book_ID = %s
    """, (book_id,))
    
    # Check if return is late and create penalty if needed
    if today > due_date:
        days_late = (today - due_date).days
        late_fee = Decimal(days_late * 0.50)  # $0.50 per day late
        
        cur.execute("""
            INSERT INTO Penalty (Late_Fee, Date_Issued, Date_Returned, Booking_ID)
            VALUES (%s, %s, %s, %s)
        """, (late_fee, today, today, booking_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect(url_for("my_books"))

# Add a route to view penalties
@app.route("/penalties")
def view_penalties():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.PenaltyID, p.Late_Fee, p.Date_Issued, p.Date_Returned, 
               p.Payment_Date, b.Booking_ID, bk.Book_Title
        FROM Penalty p
        JOIN Booking b ON p.Booking_ID = b.Booking_ID
        JOIN Book bk ON b.Book_ID = bk.Book_ID
        WHERE b.User_ID = %s
        ORDER BY p.Date_Issued DESC
    """, (user_id,))
    
    penalties = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template("penalties.html", penalties=penalties)

# Add a route to pay penalties
@app.route("/pay-penalty/<int:penalty_id>", methods=["POST"])
def pay_penalty(penalty_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    today = date.today()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verify the penalty belongs to the user
    cur.execute("""
        SELECT p.PenaltyID
        FROM Penalty p
        JOIN Booking b ON p.Booking_ID = b.Booking_ID
        WHERE p.PenaltyID = %s AND b.User_ID = %s AND p.Payment_Date IS NULL
    """, (penalty_id, user_id))
    
    if not cur.fetchone():
        cur.close()
        conn.close()
        return "Invalid penalty", 403
    
    # Update the penalty with payment date
    cur.execute("""
        UPDATE Penalty
        SET Payment_Date = %s
        WHERE PenaltyID = %s
    """, (today, penalty_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect(url_for("view_penalties"))

if __name__ == "__main__":
    app.run(debug=True)
