from pickle import NEWOBJ_EX
import requests
from flask import Flask, session, redirect, render_template, jsonify, request
import pymysql
pymysql.install_as_MySQLdb()
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

DEFAULT_INTERVAL = 60
count = DEFAULT_INTERVAL

url = "http://10.10.251.18/json/all.json"

app = Flask(__name__)
app.secret_key = 'ana_are_mere_si_bogdan_pere'

db = pymysql.connect(host="10.10.20.59", user="user1", password="1234", database="db1")

GOOGLE_CLIENT_ID = "322017813303-eham86959grnjij3gp5jr4g3jqu2stfl.apps.googleusercontent.com"

@app.route('/')
def open_page():
    if 'user' in session:
        return redirect('/main-page')
    return render_template('welcome-page.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        user = request.form['user']
        password = request.form['password']

        cursor = db.cursor()

        try:
            query = "SELECT idUSER, email, username FROM USERS WHERE email = %s OR username = %s"
            cursor.execute(query, (user, user))
            response = cursor.fetchone()
            if response:
                query = "SELECT password_hash FROM USERS WHERE email = %s OR username = %s"       
                cursor.execute(query, (user, user))
                password_hash = cursor.fetchone()
                if password_hash[0] == password:
                    session['is_authenticated'] = True
                    session['user'] = user
                    session['user_id'] = response[0]
                    return redirect('/main-page')
                else:
                    return render_template('login.html', error='Invalid username or password')
            else:
                return render_template('login.html', error='Invalid username or password')

        except Exception as e:
            print(f"Eroare la verificarea datelor: {e}")
            return render_template('login.html', error='Invalid username or password')

        finally:
            cursor.close()
    
    return render_template('login.html')

@app.route('/login/google/authorized', methods=['POST'])
def google_authorized():
    data = request.get_json()
    token = data.get('credential')

    if not token:
        return jsonify({"success": False, "message": "Token inexistent"}), 400

    try:
        # Verify tokens from Google services
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)

        # Extract Google profile info
        email = id_info.get('email')
        full_name = id_info.get('name')
        google_id = id_info.get('sub') 

        # check email in database
        cursor = db.cursor()
        query = "SELECT idUSER, username FROM USERS WHERE email = %s"
        cursor.execute(query, (email,))
        user_row = cursor.fetchone()

        if user_row:
            # if user exists -> autologin
            user_id = user_row[0]
            username = user_row[1]
        else:
            # new user -> save user's info in database
            base_username = email.split('@')[0]
            username = base_username

            query_insert = """
                INSERT INTO USERS (username, password_hash, full_name, email, created_at) 
                VALUES (%s, 'GOOGLE_AUTH', %s, %s, NOW())
            """
            cursor.execute(query_insert, (username, full_name, email))
            db.commit()
            
            user_id = cursor.lastrowid

        cursor.close()

        # Flask session info
        session['is_authenticated'] = True
        session['user'] = username
        session['user_id'] = user_id

        return jsonify({"success": True})

    except ValueError:
        # Token invalid or expired
        return jsonify({"success": False, "message": "Token invalid"}), 400
    except Exception as e:
        print(f"Eroare la autentificarea Google: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/sign-up', methods=['GET', 'POST'])
def sign_up_page():
    cursor = db.cursor()

    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
    else:
        return render_template('sign-up.html')
        
    try:
        query = "INSERT INTO USERS (username, password_hash, full_name, email, created_at) VALUES (%s, %s, %s, %s, NOW())"
        cursor.execute(query, (username, password, name, email,))
        db.commit()
    
    except Exception as e:
        db.rollback()
        print(f"Eroare la salvare: {e}")
    
    finally:
        cursor.close()

    return redirect('/login')


@app.route('/check-username')
def check_username():
    username = request.args.get('username')

    cursor = db.cursor()

    try:
        query = "SELECT username FROM USERS WHERE username = %s"
        cursor.execute(query, (username,))
        response = cursor.fetchone()
        if response:
            return jsonify({'exists': True})
        else:
            return jsonify({'exists': False})

    except Exception as e:
        print("Eroare la verificare username: {e}")
        return jsonify({'exists': False})

    finally:
        cursor.close()

@app.route('/check-email')
def check_email():
    email = request.args.get('email')

    cursor = db.cursor()

    try:
        query = "SELECT email FROM USERS WHERE email = %s"
        cursor.execute(query, (email,))
        response = cursor.fetchone()
        if response:
            return jsonify({'exists': True})
        else:
            return jsonify({'exists': False})

    except Exception as e:
        print("Eroare la verificare username: {e}")
        return jsonify({'exists': False})

    finally:
        cursor.close()

@app.route('/main-page')
def main_page():
    if 'user' in session:
        return render_template('main-page.html')
    return render_template('welcome-page.html')

@app.route('/logout')
def logout():
    session['is_authenticated'] = False
    session.pop('user', None)
    return redirect('/')

@app.route('/sensor-data')
def data_colect():
    global count
    data = requests.get(url) # request data from the device
    data = data.json() # parse the data
    new_temp = data["ds1"] # get information from sensor
    new_temp = (float(new_temp)) / 10 # convert to Celsius

    check_for_anomalies(new_temp)

    if count == 1:
        count = DEFAULT_INTERVAL
        cursor = db.cursor()

        try:
            query = "INSERT INTO MEASUREMENTS (idSENSORS, timestamp_utc, value) VALUES (1, NOW(), %s)"
            cursor.execute(query, (new_temp,))
            db.commit()

            '''
            query = "SELECT value FROM MEASUREMENTS ORDER BY idMEASUREMENTS DESC LIMIT 1"
            cursor.execute(query)
            response = cursor.fetchone()
            temperature = response[0]
            temperature = new_temp
            '''

        except Exception as e:
            db.rollback()
            print("Eroare la salvare: {e}")

        finally:
            cursor.close()
    else:
        count = count - 1

    return jsonify({"temperature": new_temp})

def check_for_anomalies(valoare_temperatura):
    # Determină severitatea în funcție de pragurile stabilite
    severitate_curenta = None
    mesaj_alarma = ""
    
    if valoare_temperatura >= 32.0 or valoare_temperatura <= 10.0:
        severitate_curenta = 'critical'
        mesaj_alarma = f"Alertă Critică: Temperatură extremă de {valoare_temperatura}°C!"
    elif valoare_temperatura >= 28.0 or valoare_temperatura <= 17.0:
        severitate_curenta = 'warning'
        mesaj_alarma = f"Atenție (Warning): Temperatură neobișnuită de {valoare_temperatura}°C!"

    db.ping(reconnect=True)
    cursor = db.cursor()
    try:
        # 1. Verificăm dacă există o alarmă deschisă în acest moment (ACTIVE sau ACKNOWLEDGED)
        # Selectăm idALARM, severity ȘI status ca să le avem pe toate trei în tuplu (evită index out of range)
        cursor.execute("SELECT idALARM, severity, status FROM ALARMS WHERE status IN ('ACTIVE', 'ACKNOWLEDGED') ORDER BY idALARM DESC LIMIT 1")
        alarma_activa = cursor.fetchone() # Returnează (idALARM, severity, status) sau None
        
        if severitate_curenta:
            # Dacă avem o stare de alertă acum...
            if not alarma_activa:
                # Cazul A: Creăm o alarmă nouă
                query_insert = """
                    INSERT INTO ALARMS (idSENSORS, severity, message, alarm_value, started_at, status)
                    VALUES (1, %s, %s, %s, NOW(), 'ACTIVE')
                """
                cursor.execute(query_insert, (severitate_curenta, mesaj_alarma, valoare_temperatura))
                db.commit()
                print("Alarma nouă a fost salvată în baza de date.")
                
            elif alarma_activa[1] != severitate_curenta:
                # Cazul B: S-a schimbat severitatea
                # O trecem pe cea veche în ACKNOWLEDGED ca să nu dispară din clopoțel până nu îi dai manual "X"
                cursor.execute("UPDATE ALARMS SET status = 'ACKNOWLEDGED', ended_at = NOW() WHERE idALARM = %s", (alarma_activa[0],))
                
                # Deschidem una nouă cu noua severitate
                query_insert = """
                    INSERT INTO ALARMS (idSENSORS, severity, message, alarm_value, started_at, status)
                    VALUES (1, %s, %s, %s, NOW(), 'ACTIVE')
                """
                cursor.execute(query_insert, (severitate_curenta, mesaj_alarma, valoare_temperatura))
                db.commit()
                
        else:
            # Cazul C: Dacă temperatura a revenit la normal
            # Verificăm direct starea [2] din primul query, fiindcă acum am selectat-o corect
            if alarma_activa and alarma_activa[2] == 'ACTIVE':
                # O remediem automat (RESOLVED) doar dacă era neatinsă (starea ACTIVE)
                query_resolve = """
                    UPDATE ALARMS 
                    SET status = 'RESOLVED', ended_at = NOW() 
                    WHERE idALARM = %s
                """
                cursor.execute(query_resolve, (alarma_activa[0],))
                db.commit()
                print("Temperatura a revenit la normal. Alarma a fost marcată ca RESOLVED.")

    except Exception as e:
        print(f"Eroare la procesare stări alarme: {e}")
    finally:
        cursor.close()

@app.route('/get-notifications')
def get_notifications():
    db.ping(reconnect=True)
    cursor = db.cursor()
    # MODIFICARE: Am adăugat coloana 'severity' în SELECT
    try:
        query = """
            SELECT A.idALARM, A.message, A.severity, U.full_name 
            FROM ALARMS A
            LEFT JOIN USERS U ON A.idUSER = U.idUSER 
            WHERE A.status IN ('ACTIVE', 'ACKNOWLEDGED') 
            ORDER BY A.idALARM DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
    
    # MODIFICARE: Adăugăm row[2] sub cheia "severity" în dicționar
        notifications = [
            {
                "id": row[0], 
                "message": row[1], 
                "severity": row[2],
                "name": row[3]
            } for row in rows
        ]
        return jsonify(notifications)
    
    except Exception as e:
        print(f"Eroare la get-notifications: {e}")
        return jsonify([])

    finally:
        cursor.close()

@app.route('/history-data')
def history_data():

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    cursor = db.cursor()
    try:
        query = "SELECT timestamp_utc, value FROM MEASUREMENTS WHERE timestamp_utc BETWEEN %s AND %s ORDER BY timestamp_utc ASC"
        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        stamps = []
        temperatures = []

        for row in rows:
            iso_date = row[0].isoformat() + 'Z' 
            stamps.append(iso_date)
            temperatures.append(row[1])

    except Exception as e:
        print(f"Eroare la extragere istoric: {e}")

    finally:
        cursor.close()
    
    return jsonify({"labels": stamps, "temperatures": temperatures})

@app.route('/resolve-alarm/<int:alarm_id>', methods=['POST'])
def resolve_alarm(alarm_id):
    cursor = db.cursor()
    try:
        # Setăm statusul ca RESOLVED și salvăm timpul rezolvării (ended_at)
        query = """
            UPDATE ALARMS 
            SET status = 'RESOLVED', 
                ended_at = NOW() 
            WHERE idALARM = %s
        """
        cursor.execute(query, (alarm_id,))
        db.commit()
    except Exception as e:
        print(f"Eroare la rezolvarea alarmei {alarm_id}: {e}")
    finally:
        cursor.close()
    return jsonify({"status": "success"})

@app.route('/read-notifications', methods=['POST'])
def read_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"status": "error", "message": "User not logged in"}), 401

    db.ping(reconnect=True)
    cursor = db.cursor()
    try:
        cursor.execute("SELECT full_name FROM USERS WHERE idUSER = %s", (user_id,))
        user_row = cursor.fetchone()
        
        # Dacă găsim numele, îl folosim; dacă nu, punem un fallback de siguranță
        full_name = user_row[0] if user_row else "Unknown User"
        # Schimbăm statusul din ACTIVE în ACKNOWLEDGED și completăm cine și când a dat click
        query = """
            UPDATE ALARMS 
            SET status = 'ACKNOWLEDGED', 
                idUSER = %s,
                acknowledged_by = %s,
                acknowledged_at = NOW() 
            WHERE status = 'ACTIVE'
        """
        cursor.execute(query, (user_id, full_name))
        db.commit()
    except Exception as e:
        print(f"Eroare la confirmare alarme: {e}")
    finally:
        cursor.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run()

