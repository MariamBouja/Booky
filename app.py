from flask import Flask, request, session, redirect, url_for, jsonify, render_template, flash
from flask_bcrypt import Bcrypt
from functools import wraps
import psycopg2
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
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


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

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    role = session.get('role')

    if not user_id or not role:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()

    if role == "admin":
        cur.execute("SELECT * FROM admin_view WHERE user_id = %s", (user_id,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('admin_dashboard.html', data=data)

    elif role == "student":
        cur.execute("SELECT * FROM student_view WHERE user_id = %s", (user_id,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('student_dashboard.html', data=data)

    elif role == "professor":
        cur.execute("SELECT * FROM professor_view WHERE user_id = %s", (user_id,))
        data = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('professor_dashboard.html', data=data)

    else:
        return "Unknown role", 400

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            au.User_Fname || ' ' || COALESCE(au.User_Mname || ' ', '') || au.User_Lname AS user_name,
            b.Book_Title,
            bk.Booking_Date,
            bk.Due_Date,
            bk.Return_Date
        FROM Booking bk
        JOIN AppUser au ON bk.User_ID = au.User_ID
        JOIN Book b ON bk.Book_ID = b.Book_ID;
    """)

    rows = cur.fetchall()
    data = []
    for row in rows:
        data.append({
            "user_name": row[0],
            "book_title": row[1],
            "booking_date": row[2],
            "due_date": row[3],
            "return_date": row[4]
        })

    cur.close()
    conn.close()

    
    print("Data for admin dashboard:", data)

    return render_template("admin_dashboard.html", data=data)



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))



@app.route("/books")
def list_books():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            book.book_id, 
            book.book_title, 
            CONCAT(author.author_fname, ' ', 
                   COALESCE(author.author_mname || ' ', ''), 
                   author.author_lname) AS full_name,
            book.genre, 
            book.book_language, 
            book.available_copies,
            book.book_image
        FROM book
        JOIN author ON book.author_id = author.author_id
        WHERE book.available_copies > 0;
    """)

    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("books.html", books=books)

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    # Search in book titles and author names
    cur.execute("""
        SELECT 
            b.book_id, b.book_title,
            CONCAT(a.author_fname, ' ', COALESCE(a.author_mname || ' ', ''), a.author_lname) AS author_name,
            b.genre, b.book_language, b.available_copies, b.book_image
        FROM book b
        JOIN author a ON b.author_id = a.author_id
        WHERE 
            LOWER(b.book_title) LIKE LOWER(%s) OR
            LOWER(a.author_fname) LIKE LOWER(%s) OR
            LOWER(a.author_lname) LIKE LOWER(%s)
    """, (f"%{query}%", f"%{query}%", f"%{query}%"))

    results = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("search.html", query=query, results=results)


@app.route("/suggest")
def suggest():
    term = request.args.get("term", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT book_title FROM book
        WHERE LOWER(book_title) LIKE LOWER(%s)
        LIMIT 5
    """, (f"{term}%",))

    titles = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    return jsonify(titles)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fname = request.form["first_name"]
        lname = request.form["last_name"]
        phone = request.form["phone"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # Check for existing email
            cur.execute("SELECT 1 FROM Appuser WHERE email = %s", (email,))
            if cur.fetchone():
                return "Email already registered.", 400

            # Generate new ID
            cur.execute("SELECT COALESCE(MAX(user_id), 100) + 1 FROM Appuser")
            new_user_id = cur.fetchone()[0]

            is_admin = role == "admin"
            is_student = role == "student"
            is_professor = role == "professor"

            # Insert into Appuser
            cur.execute("""
                INSERT INTO Appuser (user_id, user_fname, user_lname, phone, email, password,
                                     user_is_admin, user_is_student, user_is_instructor)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (new_user_id, fname, lname, phone, email, hashed_password,
                  is_admin, is_student, is_professor))

            # Add to role-specific table
            if is_student:
                cur.execute("INSERT INTO Student (user_id, major, academic_year) VALUES (%s, '', '')", (new_user_id,))
            elif is_professor:
                cur.execute("INSERT INTO Professor (user_id, office_number, school_department) VALUES (%s, '', '')", (new_user_id,))
            elif is_admin:
                cur.execute("INSERT INTO Admin (user_id, admin_role) VALUES (%s, 'Librarian')", (new_user_id,))

            conn.commit()

            # Set session and redirect
            session["user_id"] = new_user_id
            session["role"] = role  # just store the string "admin", "student", or "professor"
            return redirect(url_for("dashboard"))

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
        cur.execute("""
            SELECT user_id, password, user_is_admin, user_is_student, user_is_instructor
            FROM Appuser WHERE email = %s
        """, (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user[1] and bcrypt.check_password_hash(user[1], password):
            session["user_id"] = user[0]
            # Set role
            if user[2]:  # admin
                session["role"] = "admin"
            elif user[3]:  # student
                session["role"] = "student"
            elif user[4]:  # instructor
                session["role"] = "instructor"

            return redirect(url_for("dashboard"))
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

@app.route('/review', methods=['GET', 'POST'])
def review():
    if request.method == 'POST':
        book_id = request.form['book_id']
        rating = request.form['rating']
        review_text = request.form['review_text']
        user_id = session.get('user_id')

        if not user_id:
            flash("You must be logged in to submit a review.", "danger")
            return redirect('/login')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO reviews (user_id, book_id, rating, review_text)
                VALUES (%s, %s, %s, %s)
            """, (user_id, book_id, rating, review_text))
            conn.commit()
            flash("Thank you for your review!", "success")
        except Exception as e:
            print("Error submitting review:", e)
            flash("Something went wrong. Try again.", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect('/')

    # GET: Load books into the dropdown
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT book_id, book_title FROM book")
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("review.html", books=books)


@app.route('/review/<int:book_id>', methods=['POST'])
def add_review(book_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))  # or handle unauthenticated users

    user_id = session['user_id']
    comment = request.form['comment']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO Review (User_ID, Book_ID, Comment, Date_Issued)
        VALUES (%s, %s, %s, CURRENT_DATE)
        ON CONFLICT (User_ID, Book_ID) DO UPDATE 
        SET Comment = EXCLUDED.Comment, Date_Issued = EXCLUDED.Date_Issued;
    """, (user_id, book_id, comment))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('book_detail', book_id=book_id))

@app.route('/books/<int:book_id>/review', methods=['POST'])
def submit_review(book_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    comment = request.form.get('comment')
    date_issued = datetime.now().date()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO Review (User_ID, Book_ID, Comment, Date_Issued)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (User_ID, Book_ID) DO UPDATE 
        SET Comment = EXCLUDED.Comment, Date_Issued = EXCLUDED.Date_Issued
    """, (user_id, book_id, comment, date_issued))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('book_detail', book_id=book_id))



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

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Get book info
    cur.execute("SELECT * FROM Book WHERE book_id = %s", (book_id,))
    book = cur.fetchone()

    # Get author info
    cur.execute("""
        SELECT a.author_fname, a.author_lname
        FROM Author a
        JOIN Book b ON a.author_id = b.author_id
        WHERE b.book_id = %s
    """, (book_id,))
    author = cur.fetchone()

    # Get reviews and user names
    cur.execute("""
        SELECT r.comment, r.date_issued, u.user_fname || ' ' || u.user_lname as user_name
        FROM Review r
        JOIN Appuser u ON r.user_id = u.user_id
        WHERE r.book_id = %s
        ORDER BY r.date_issued DESC
    """, (book_id,))
    reviews = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("book_detail.html", book=book, author=author, reviews=reviews)




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
        SELECT p.penalty_id, p.late_fee, p.date_issued, p.date_returned, 
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
        SELECT p.penalty_id
        FROM penalty p
        JOIN booking b ON p.booking_id = b.booking_id
        WHERE p.penalty_id = %s AND b.user_id = %s AND p.payment_date IS NULL
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
