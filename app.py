from flask import Flask
import psycopg2
from psycopg2 import sql
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
 
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
if __name__ == "__main__":
    app.run(debug=True)