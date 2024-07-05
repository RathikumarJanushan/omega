import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import cv2
from pyzbar.pyzbar import decode

camera_url = "http://192.168.8.171:8080/video"

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Use a more secure secret key
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Function to connect to the database
def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host='localhost',      # MySQL server host
            user='root',           # MySQL username
            database='omega'       # The database name
        )
        if connection.is_connected():
            print("Connected to the database")
        return connection
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

# Route for the home page
@app.route('/')
def home():
    return render_template('home.html')

# Route for the sign-up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        db_connection = connect_to_database()
        if db_connection:
            cursor = db_connection.cursor()
            query = "INSERT INTO username (username, password) VALUES (%s, %s)"
            cursor.execute(query, (username, hashed_password))
            db_connection.commit()
            cursor.close()
            db_connection.close()
        return redirect(url_for('home'))
    return render_template('signup.html')

# Route for the sign-in page
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db_connection = connect_to_database()
        if db_connection:
            cursor = db_connection.cursor()
            query = "SELECT password FROM username WHERE username = %s"
            cursor.execute(query, (username,))
            result = cursor.fetchone()
            cursor.close()
            db_connection.close()
            
            if result and check_password_hash(result[0], password):
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                return "Invalid username or password"
    return render_template('signin.html')

@app.route('/admin_signin', methods=['GET', 'POST'])
def admin_signin():
    if request.method == 'POST':
        if 'admin_name' not in request.form or 'password' not in request.form:
            return "Missing admin_name or password"

        admin_name = request.form['admin_name']
        password = request.form['password']
        
        db_connection = connect_to_database()
        if db_connection:
            cursor = db_connection.cursor()
            query = "SELECT password FROM admin WHERE admin_name = %s"
            cursor.execute(query, (admin_name,))
            result = cursor.fetchone()
            cursor.close()
            db_connection.close()
            
            if result and result[0] == password:  # Direct comparison for plain text passwords
                session['admin_name'] = admin_name
                return redirect(url_for('dashboard2'))
            else:
                return "Invalid admin_name or password"
    return render_template('admin.html')
@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        db_connection = connect_to_database()
        if db_connection:
            cursor = db_connection.cursor(dictionary=True)
            select_query = """
            SELECT DATE_FORMAT(scan_time, '%Y-%m-%d') as scan_time, batch, hu, material, start_w, middle_w, end_w
            FROM history
            WHERE username = %s
            ORDER BY scan_time DESC
            """
            cursor.execute(select_query, (session['username'],))
            history_data = cursor.fetchall()
            cursor.close()
            db_connection.close()
            return render_template('main.html', username=session['username'], history_data=history_data)
    return redirect(url_for('signin'))



# Route for the admin dashboard page
@app.route('/dashboard2')
def dashboard2():
    if 'admin_name' in session:
        return render_template('AdminHome.html', admin_name=session['admin_name'])
    return redirect(url_for('signin'))

# Route for logout
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    session.pop('admin_name', None)
    return redirect(url_for('home'))

# Function to get the current logged-in user's username
def get_current_username():
    return session.get('username')

@app.route('/start_scan', methods=['GET'])
def start_scan():
    # Access the camera feed and scan the QR code
    cap = cv2.VideoCapture(camera_url)
    success, frame = cap.read()
    if success:
        decoded_objects = decode(frame)
        if decoded_objects:
            qr_text = decoded_objects[0].data.decode('utf-8')
            
            # Connect to the database and check the QR code against the HU column
            db_connection = connect_to_database()
            if db_connection:
                cursor = db_connection.cursor()
                query = "SELECT BATCH, HU, MATERIAL FROM masterdata WHERE HU = %s"
                cursor.execute(query, (qr_text,))
                result = cursor.fetchone()
                
                if result:
                    batch, hu, material = result
                    username = get_current_username()  # Retrieve the current username

                    # Insert into the history table
                    insert_query = """
                    INSERT INTO history (batch, hu, material, username)
                    VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (batch, hu, material, username))
                    db_connection.commit()

                    cursor.close()
                    db_connection.close()

                    return jsonify({'success': True, 'batch': batch, 'hu': hu, 'material': material})
                else:
                    cursor.close()
                    db_connection.close()
                    return jsonify({'success': False, 'error': 'No matching data found for the scanned QR code.'}), 404
        return jsonify({'success': False, 'error': 'No QR code found in the camera feed.'}), 400
    return jsonify({'success': False, 'error': 'Failed to access the camera feed.'}), 500

# Route to upload file and add master data
@app.route('/upload_file', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    if file and file.filename.endswith(('xlsx', 'xls')):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Process the Excel file
        data = pd.read_excel(filepath)
        if set(['BATCH', 'HU', 'MATERIAL']).issubset(data.columns):
            batch_hu_material_data = data[['BATCH', 'HU', 'MATERIAL']].drop_duplicates(subset=['HU'])

            db_connection = connect_to_database()
            if db_connection:
                cursor = db_connection.cursor()
                for index, row in batch_hu_material_data.iterrows():
                    cursor.execute("SELECT COUNT(*) FROM masterdata WHERE HU = %s", (row['HU'],))
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("INSERT INTO masterdata (BATCH, HU, MATERIAL) VALUES (%s, %s, %s)",
                                       (row['BATCH'], row['HU'], row['MATERIAL']))
                db_connection.commit()
                cursor.close()
                db_connection.close()
            return 'File successfully uploaded and data added'
        return 'Invalid file format'
    return 'Invalid file extension'
    return redirect(url_for('dashboard'))


@app.route('/update_start_w', methods=['POST'])
def update_start_w():
    start_w = request.form['start_w']
    username = get_current_username()

    db_connection = connect_to_database()
    if db_connection:
        cursor = db_connection.cursor()
        update_query = """
        UPDATE history
        SET start_w = %s
        WHERE username = %s
        ORDER BY id DESC
        LIMIT 1
        """
        cursor.execute(update_query, (start_w, username))
        db_connection.commit()
        cursor.close()
        db_connection.close()

    return redirect(url_for('dashboard'))


@app.route('/update_middle_w', methods=['POST'])
def update_middle_w():
    middle_w = request.form['middle_w']
    username = get_current_username()

    db_connection = connect_to_database()
    if db_connection:
        cursor = db_connection.cursor()
        update_query = """
        UPDATE history
        SET middle_w = %s
        WHERE username = %s
        ORDER BY id DESC
        LIMIT 1
        """
        cursor.execute(update_query, (middle_w, username))
        db_connection.commit()
        cursor.close()
        db_connection.close()

    return redirect(url_for('dashboard'))

@app.route('/update_end_w', methods=['POST'])
def update_end_w():
    end_w = request.form['end_w']
    username = get_current_username()

    db_connection = connect_to_database()
    if db_connection:
        cursor = db_connection.cursor()
        update_query = """
        UPDATE history
        SET end_w = %s
        WHERE username = %s
        ORDER BY id DESC
        LIMIT 1
        """
        cursor.execute(update_query, (end_w, username))
        db_connection.commit()
        cursor.close()
        db_connection.close()

    return redirect(url_for('dashboard'))

# Route to fetch and display history for the admin
@app.route('/view_history', methods=['GET'])
def view_history():
    db_connection = connect_to_database()
    if db_connection:
        cursor = db_connection.cursor(dictionary=True)
        select_query = """
        SELECT username, scan_time, batch, hu, material, start_w, middle_w, end_w
        FROM history
        ORDER BY scan_time DESC
        """
        cursor.execute(select_query)
        history_data = cursor.fetchall()
        cursor.close()
        db_connection.close()

        return render_template('view_history.html', history_data=history_data)

    return jsonify([]), 500






if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
