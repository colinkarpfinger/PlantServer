from flask import Flask, render_template, send_file, make_response, request, url_for, session, g, flash, redirect, Response
from gpiozero import CPUTemperature 
from datetime import datetime
import sqlite3
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import io
import os
import functools 
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash
from camera import Webcam

import sys
import contextlib


class DummyFile(object):
    def write(self, x): pass

@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = DummyFile()
    yield
    sys.stdout = save_stdout


app = Flask(__name__)
app.config.from_mapping(SECRET_KEY='yoursecretkeyhere')

app.add_url_rule("/", endpoint="index")
db = 'db/sensorData.db'


def login_required(view):
    """View decorator that redirects anonymous users to the login page."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        print(g.user)
        if g.user is None:
            return redirect("/login")

        return view(**kwargs)

    return wrapped_view


@app.before_request
def load_logged_in_user():
    """If a user id is stored in the session, load the user object from
    the database into ``g.user``."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        conn = sqlite3.connect(db) 
        curs = conn.cursor()
        g.user = (
            curs.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        )


def getLastDataPi():
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor()
    for row in curs.execute('SELECT * FROM pi_data ORDER BY timestamp DESC LIMIT 1'):
        time = str(row[0])
        temp = row[1]
        ram_perc_used = row[2]
    conn.commit()
    return time, temp, ram_perc_used

def GetPlantGpioAndDurationPref(plantName ):
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 
    plantNameTuple = (plantName.lower(),)       # take lowercase string in case it was capitalized. lowercase plant names are used in the db
    curs.execute('SELECT gpio_number, duration_pref_seconds FROM plant_config WHERE plant_name = ?', plantNameTuple)
    result = curs.fetchone()
    gpioNumber = result[0]
    durationPrefSeconds = result[1]
    return gpioNumber, durationPrefSeconds;

def GetPlantAdcChannel(plantName):
    conn = sqlite3.connect(db)
    curs = conn.cursor() 
    plantNameTuple = (plantName.lower(),)       # take lowercase string in case it was capitalized. lowercase plant names are used in the db
    curs.execute('SELECT adc_channel FROM plant_config WHERE plant_name = ?', plantNameTuple)  
    plantAdcChannel = int(curs.fetchone()[0])
    return plantAdcChannel

def GetPlantSoilMoisture(plantName):
    conn = sqlite3.connect(db)
    curs = conn.cursor() 
    plantNameTuple = (plantName.lower(),)       # take lowercase string in case it was capitalized. lowercase plant names are used in the db
    curs.execute('SELECT adc_channel FROM plant_config WHERE plant_name = ?', plantNameTuple)  
    plantAdcChannel = int(curs.fetchone()[0])
    curs.execute('SELECT count FROM adc_data WHERE channel = ? ORDER BY timestamp DESC LIMIT 1', (plantAdcChannel,))
    result = curs.fetchone()
    if result is not None:
        plantAdcCount = int(result[0])
    else:
        plantAdcCount = 26400
    moisture = (26400 - plantAdcCount)/26400
    return moisture

def GetPlantLastWateredDateTime(plantName):
    conn = sqlite3.connect(db)
    curs = conn.cursor() 
    curs.execute('SELECT gpio_number FROM plant_config WHERE plant_name = ?',(plantName.lower(),))  
    gpioNumber = int(curs.fetchone()[0])

    plantNameTuple = (plantName.lower(),)       # take lowercase string in case it was capitalized. lowercase plant names are used in the db
    curs.execute('SELECT timestamp FROM pump_status WHERE gpio_number = ? AND status = ? ORDER BY timestamp DESC LIMIT 1', (gpioNumber,'running',))
    lastWateredDateTime = str(curs.fetchone()[0])
    return lastWateredDateTime

def GetPlantLastWateredHoursAgo(plantName):
    lastWateredDateTime = GetPlantLastWateredDateTime(plantName)
    datetime_object = datetime.strptime(lastWateredDateTime, '%Y-%m-%d %H:%M:%S') 
    lastWateredHours = (datetime.utcnow()- datetime_object).total_seconds() / 3600
    print ('last watered hours:'+str(lastWateredHours))
    return lastWateredHours

def PumpRequestRun(gpioNumber, durationSeconds):
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 
    
    curs.execute('INSERT INTO pump_status values(datetime("now"), (?), (?), (?))', (gpioNumber, 'requestrun', durationSeconds))
    conn.commit() 
    return 

def GetHistPlantMoistureData (plantName, numSamples):
    plantAdcChannel = GetPlantAdcChannel(plantName)
    

    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 

    curs.execute('SELECT timestamp, count FROM adc_data WHERE channel = ? ORDER BY timestamp DESC LIMIT ?',(plantAdcChannel, str(numSamples)))
    data = curs.fetchall()
    timestamp_data = []
    moisture_count_data = []
    for row in reversed(data):
        timestamp_data.append(row[0])
        moisture_count_data.append(row[1])
    
    conn.commit()
    return timestamp_data,moisture_count_data 


def getHistData (numSamples):
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 

    curs.execute('SELECT * FROM pi_data ORDER BY timestamp DESC LIMIT '+str(numSamples))
    data = curs.fetchall()
    date_data = []
    temp_data = []
    ram_data = []
    for row in reversed(data):
        date_data.append(row[0])
        temp_data.append(row[1])
        ram_data.append(row[2])
    
    conn.commit()
    return date_data,temp_data,ram_data

def maxRowsTable():
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 
    for row in curs.execute('SELECT COUNT(temp) FROM pi_data'):
        maxNumRows = row[0]
    conn.commit()
    return maxNumRows

def maxRowsAdcTable():
    conn = sqlite3.connect('db/sensorData.db')
    curs = conn.cursor() 
    for row in curs.execute('SELECT COUNT(count) FROM adc_data'):
        maxNumRows = row[0]
    conn.commit()
    return maxNumRows


#define global variables 
global numSamples, numSamplesAdc
numSamples = maxRowsTable()
numSamplesAdc = maxRowsAdcTable()
if (numSamples > 201):
    numSamples = 200



@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(db)
        curs = conn.cursor() 
        error = None
        user = curs.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        #print (user)
        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user[2], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user[0]
            #print(session['user_id'])
            return redirect("/")

        flash(error)

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route("/")
@login_required
def index():
    now = datetime.now()
    timeString = now.strftime("%Y-%m-%d %H:%M")
    cpu = CPUTemperature()
    cpuTempString = str(cpu.temperature)

    time, temp, ram_perc_used = getLastDataPi()
    #print(ram_perc_used)
    templateData = {
            'title': 'Plant Server',
            'time': time,
            'cpu_temp': str(int(round(temp,0))), 
            'ram_perc_used': str(int(round(ram_perc_used * 100,0 )))
            }
    return render_template('main.html', **templateData)

@app.route('/', methods=['POST'])
@login_required
def my_form_post():
    global numSamples
    numSamples = int (request.form['numSamples'])
    numMaxSamples = maxRowsTable()
    if (numSamples > numMaxSamples):
        numSamples = numMaxSamples-1
    time,temp,ram_perc_used = getLastDataPi()
    templateData = {
            'title': 'Plant Server',
            'time': time,
            'cpu_temp': temp,
            'ram_perc_used': str(round(ram_perc_used, 3)*100 )
            }
    return render_template('main.html', **templateData)

@app.route('/plot/temp')
@login_required
def plot_temp():
	times, temps, rams = getHistData(numSamples)
	ys = temps
	fig = Figure()
	axis = fig.add_subplot(1, 1, 1)
	axis.set_title("Temperature [C]")
	axis.set_xlabel("Samples")
	axis.grid(True)
	xs = range(numSamples)
	axis.plot(xs, ys)
	canvas = FigureCanvas(fig)
	output = io.BytesIO()
	canvas.print_png(output)
	response = make_response(output.getvalue())
	response.mimetype = 'image/png'
	return response

def MakePlantPlot(plantName):
    times, moistures = GetHistPlantMoistureData(plantName, numSamplesAdc)
    ys = moistures
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    axis.set_title("Moisture Count: "+plantName)
    axis.set_xlabel("Samples")
    axis.grid(True)
    axis.set_ylim(9000,17000)
    xs = range(numSamplesAdc)
    axis.plot(xs, ys)
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    canvas.print_png(output)
    response = make_response(output.getvalue())
    response.mimetype = 'image/png'
    return response


@app.route('/plot/ram')
@login_required
def plot_ram():
	times, temps, rams = getHistData(numSamples)
	ys = rams
	fig = Figure()
	axis = fig.add_subplot(1, 1, 1)
	axis.set_title("RAM Usage [%]")
	axis.set_xlabel("Samples")
	axis.grid(True)
	xs = range(numSamples)
	axis.plot(xs, ys)
	canvas = FigureCanvas(fig)
	output = io.BytesIO()
	canvas.print_png(output)
	response = make_response(output.getvalue())
	response.mimetype = 'image/png'
	return response

@app.route('/plot/herbs')
@login_required
def plot_herbs():
    return MakePlantPlot('herbs')

@app.route('/plot/tree')
@login_required
def plot_tree():
    return MakePlantPlot('tree')

@app.route('/plot/fred')
@login_required
def plot_fred():
    return MakePlantPlot('fred')


@app.route('/plot/amp')
@login_required
def plot_amp():
    return MakePlantPlot('amp')


@app.route('/plants-graphs', methods=['GET', 'POST'])
@login_required
def plants_graphs():
    
    global numSamplesAdc
    if request.method == 'POST':
        numSamplesAdc = int (request.form['numSamples'])
    else:
        numSamplesAdc = 200
    numMaxSamplesAdc = maxRowsAdcTable()
    if numSamplesAdc > numMaxSamplesAdc:
        numSamplesAdc = numMaxSamplesAdc-1
    templateData = {
            'title': 'Moisture Graphs',
            }
    return render_template('plants-graphs.html', **templateData)

    

@app.route('/plants')
@login_required
def plants_page():
    templateData = {}
    return render_template('plants.html', **templateData)

@app.route('/plants/detail', methods=['GET'])
@login_required
def plants_detail():
    plantName = str(request.args.get('plant_name')).capitalize()

    #request data from database 
    moisture = GetPlantSoilMoisture(plantName)
    lastWateredHours = GetPlantLastWateredHoursAgo(plantName)
    days = int(lastWateredHours / 24)
    hoursRemainder = int(lastWateredHours % 24)

    templateData = {
            'title': 'Plant Detail',
            'plant_name': plantName,
            'last_watered_days': days,
            'last_watered_hours': hoursRemainder,
            'moisture': round(moisture*100,0)
            }
    return render_template('plants-detail.html', **templateData)



@app.route('/plants/water', methods=['GET'])
@login_required
def plants_water():
    plantName = str(request.args.get('plant_name'))
    waterAmt = str(request.args.get('water_amount'))
    print('Watering '+plantName+', amount: '+waterAmt)
    
    #look up plant_config, figure out which gpio this plant is on, and duration_pref_seconds 
    #insert into pump_status: timestamp, gpio_number, status="requestrun", duration_seconds = duration_pref_seconds 
    gpioNumber, durationPrefSeconds = GetPlantGpioAndDurationPref(plantName.lower())
    durationSeconds = int(durationPrefSeconds)
    if waterAmt == '1':
        durationSeconds = durationSeconds * 0.8
    elif waterAmt == '3':
        durationSeconds = durationSeconds * 1.2

    PumpRequestRun( gpioNumber, durationSeconds);
    

    templateData = {
            'title': 'Watering',
            'plant_name': plantName,
            'water_amount': waterAmt
            }

    return render_template('watering.html', **templateData)

@app.route('/video')
@login_required
def video_page():
    return render_template('video.html')

def gen(camera):
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


@app.route('/video_feed')
@login_required
def video_feed():
    with nostdout():
        response = Response(gen(Webcam()), mimetype='multipart/x-mixed-replace; boundary=frame')
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, debug=False)

