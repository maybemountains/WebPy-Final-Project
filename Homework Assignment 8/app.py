from datetime import datetime
import random
import folium
from pymongo import MongoClient
from flask import Flask, render_template, request, redirect, url_for, flash, g 
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, HiddenField, RadioField, SelectField, StringField, PasswordField, SubmitField, TextAreaField, TimeField
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired, Length, Email
from flask_babel import gettext
from bson import ObjectId
import time
import sqlite3
from dotenv import load_dotenv
import os
from werkzeug import exceptions as werkzeugExceptions
from flask_mail import Mail, Message
from flask_babel import Babel

load_dotenv()

mongoClient = MongoClient(os.getenv('MONGO_URI'))

mongoDB = mongoClient['DriverCarsDB']
carCollection = mongoDB['carInfo']
rideCollection = mongoDB['rides']

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

app.config['LANGUAGES'] = {
    'en': 'English',
    'fr': 'French',
    'sq_AL': 'Albanian'
}

babel = Babel(app)
def get_locale():
    return request.accept_languages.best_match(app.config['LANGUAGES'].keys())
babel.init_app(app, locale_selector=get_locale)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

gay = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

bcrypt = Bcrypt(app) 

class RequestRide(FlaskForm):
    long = FloatField(gettext('Destination Longitude'), validators=[DataRequired()])
    lat = FloatField(gettext('Destination Latitude'), validators=[DataRequired()])
    pickupLong = FloatField(gettext('Pickup Longitude'), validators=[DataRequired()])
    pickupLat = FloatField(gettext('Pickup Latitude'), validators=[DataRequired()])
    time = TimeField(gettext('Time'))
    carType = SelectField(gettext('Car Type'), validators=[DataRequired()])
    cardHolderName = StringField(gettext('Card Holder Name'), validators=[DataRequired(), Length(min=4, max=320)])
    cardNumber = StringField(gettext('Card Number'), validators=[DataRequired(), Length(min=8, max=320)])
    cardExpirationDate = DateField(gettext('Card Expiration Date'))
    cardCVV = StringField(gettext('CVV'), validators=[DataRequired(), Length(min=3, max=3)])
    submit = SubmitField(gettext('Request'))

#region SQLite
# makes or gets and then returns the sqlite db
def getSQLiteDB():
    sqlDB = getattr(g, '_database', None)
    if sqlDB is None:
        sqlDB = g._database = sqlite3.connect(os.getenv('SQLITE_URI'))
        createSQLiteTable(sqlDB)
    return sqlDB

# this will create the table users in our sqlite db
def createSQLiteTable(sqlDB):
    cursor = sqlDB.cursor()
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, 
                   email TEXT, 
                   username TEXT,
                   password TEXT,
                   isDriver BOOL)""")
    sqlDB.commit()
        
#endregion 

pendingRideRequests = {}
usersWaiting = []

#region routes
# this will show the welcome page which will display the request ride form
@app.route('/', methods=['GET', 'POST'])
@login_required
def welcomePage():
        if (usersWaiting.count(current_user.id) > 0):
            return redirect('/waitForDriver')

        possibleRide = rideCollection.find_one({"riderId": current_user.id})
        if (possibleRide is not None):
            return redirect(f'/ride/{possibleRide.get("_id")}')


        possibleRide = rideCollection.find_one({"driverId": current_user.id})
        if (possibleRide is not None):
            return redirect(f'/ride/{possibleRide.get("_id")}')
        
        if (current_user.isDriver):
            return redirect('/pickRide')

        form = RequestRide()
        
        form.carType.choices = [(i['carType'], i['carType']) for i in carCollection.find()]
        if form.validate_on_submit():
            long = form.long.data 
            lat = form.lat.data
            pickupLong = form.pickupLong.data
            pickupLat = form.pickupLat.data
            time = form.time.data
            carType = form.carType.data
            cardHolderName = form.cardHolderName.data
            cardNumber = form.cardNumber.data
            cardExpirationDate = form.cardExpirationDate.data
            cardCVV = form.cardCVV.data
            if (carType not in pendingRideRequests):
                pendingRideRequests[carType] = []
            pendingRideRequests[carType].append({'long': long, 'lat': lat, 'pickupLong': pickupLong, 'pickupLat': pickupLat, 'time': time, 'carType': carType, 'cardHolderName': cardHolderName, 'cardNumber': cardNumber, 'cardExpirationDate': cardExpirationDate, 'cardCVV': cardCVV, 'riderId': current_user.id})
            usersWaiting.append(current_user.id)
            return redirect('/waitForDriver')
        # otherwise, show the ride request form.
        return render_template('requestRide.html', form=form)

@app.route('/waitForDriver')
@login_required
def waitForDriver():
    if (current_user.isDriver):
        return redirect('/')

    possibleRide = rideCollection.find_one({"riderId": current_user.id})
    if (possibleRide is not None):
        return redirect('/ride/' + str(possibleRide.get('_id')))
    
    if (possibleRide is None and usersWaiting.count(current_user.id) == 0):
        return redirect('/')

    return render_template('waitForDriver.html')

@app.route('/ridePreCancel')
@login_required
def ridePreCancel():
    if (current_user.isDriver):
        return redirect('/')
    usersWaiting.remove(current_user.id)
    for k, v in pendingRideRequests.items():
        for i in v:
            if (i.get("riderId") == current_user.id):
                pendingRideRequests[k].remove(i)
                break

    return redirect('/')

@app.route('/pickRide')
@login_required
def pickRide():
    if (not current_user.isDriver):
        return redirect('/')
    
    return render_template('pickRide.html', pendingRideRequests=pendingRideRequests)

@app.route('/selectRide/<carType>/<riderId>')
@login_required
def selectRide(carType, riderId):
    if (not current_user.isDriver or carType not in pendingRideRequests):
        return redirect('/')
    carInfo = carCollection.find_one({"driverID": current_user.id})
    cType = carInfo.get('carType')
    for i in pendingRideRequests[cType]:
        if (i.get('riderId') == int(riderId)):
            i['driverId'] = current_user.id
            i['price'] = random.randint(69, 420)
            i['chat'] = []
            # Combine with a specific date (you can adjust the date as needed)  
            i['time'] = i.get('time').strftime("%H:%M:%S")
            i['cardExpirationDate'] = i.get('cardExpirationDate').strftime("%Y-%m-%d")
            ride = rideCollection.insert_one(i)
            pendingRideRequests[cType].remove(i)
            usersWaiting.remove(riderId)
            return redirect('/ride/' + str(ride._id))
        
    return redirect('/pickRide')

@app.route('/ride/<rideId>')
@login_required
def ride(rideId):
    ride = rideCollection.find_one({"_id": ObjectId(rideId)})
    if (ride is None or (ride.get('riderId') != current_user.id and ride.get('driverId') != current_user.id)):
        return redirect('/')
    
    if (ride.get('arrived')):
        rideCollection.delete_one({"_id": ObjectId(rideId)})
        return redirect('/ride/' + rideId + '/invoice')
    # Define coordinates of points
    pickup = [float(ride['pickupLong']), float(ride['pickupLat'])]
    dest = [float(ride['long']), float(ride['lat'])]

    # Create the map
    map = folium.Map(location=pickup, zoom_start = 10)

    # Add points to the map
    folium.Marker(pickup, popup='Pickup').add_to(map)
    folium.Marker(dest, popup='Destination').add_to(map)

     # Draw line between point A and point B
    folium.PolyLine(locations=[pickup, dest], color="pink", weight=3, opacity=1).add_to(map)
    return render_template('ride.html', ride=ride, map=map._repr_html_())

class RideChatForm(FlaskForm):
    # sender = HiddenField(validators=[DataRequired()])
    message = TextAreaField(gettext('Message'), validators=[DataRequired()])
    submit = SubmitField(gettext('Send'))

@app.route('/ride/<rideId>/chat', methods=["GET", "POST"])
@login_required
def chat(rideId):
    ride = rideCollection.find_one({"_id": ObjectId(rideId)})
    if (ride is None or (ride.get("riderId") != current_user.id and ride.get("driverId") != current_user.id) or ride.get("arrived")):
        return redirect('/')
    
    form = RideChatForm()
    sender = gettext('rider') if ride.get("riderId") == current_user.id else gettext('driver')
    if (form.validate_on_submit()):
        rideCollection.update_one({"_id" : ObjectId(rideId)}, {'$push' : {'chat' : {'sender': sender, 'message': form.message.data}}})
        # rideCollection.update_one({"_id": ObjectId(rideId)}, {'$push': {'chat': {'sender': form.sender, 'message': form.message.data}}})
        return redirect('/ride/' + rideId + '/chat')

    return render_template('chat.html', ride=ride, form=form)

@app.route('/ride/<rideId>/arrived')
@login_required
def arrived(rideId):
    ride = rideCollection.find_one({"_id": ObjectId(rideId)})
    if (ride is None or (ride.get("driverId") != current_user.id) or ride.get("arrived")):
        return redirect('/')
    
    rideCollection.update_one({"_id": ObjectId(rideId)}, {'$set': {'arrived': True}})

    conn = getSQLiteDB()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE id=?", (ride.get("riderId"),))
    email = cursor.fetchone()
    msg = Message(subject="heres your invoice!", body=f"Ride for {ride.get('price')}$ completed!",
                        sender="no-reply@IT-Girl-Transport.com",
                        recipients=[current_user.email, email[0]])
    gay.send(msg)
    return redirect('/ride/' + rideId + '/invoice')

@app.route('/ride/<rideId>/invoice')
@login_required
def invoice(rideId):
    ride = rideCollection.find_one({"_id": ObjectId(rideId)})
    if (ride is None or (ride.get("riderId") != current_user.id and ride.get("driverId") != current_user.id)):
        return redirect('/')
    if (not ride.get("arrived")):
        return redirect('/ride/' + rideId)
    return render_template('invoice.html', ride=ride)

#endregion

#region errors & middleware
@app.errorhandler(werkzeugExceptions.NotFound)
def handle_not_found(e):
    return render_template("404.html")

@app.errorhandler(werkzeugExceptions.InternalServerError)
def handle_internal_server_error(e):
    return render_template("500.html")

# Middleware to log information before each request
@app.before_request
def before_request():
    g.start_time = time.time()
    print(f"Request started for {request.path} at {g.start_time}")

# Middleware to log information after each request
@app.after_request
def after_request(response):
    end_time = time.time()
    elapsed_time = end_time - g.start_time
    print(f"Request ended for {request.path} at {end_time}")
    print(f"Elapsed time: {elapsed_time} seconds")
    print(f"Status Code: {response.status_code}")
    print(f"Request Method: {request.method}")
    return response

#endregion

if __name__ == '__main__':
    import auth
    app.register_blueprint(auth.auth_blueprint)
    login_manager.user_loader(auth.load_user)
    from driverInfo import driverInfo_blueprint
    app.register_blueprint(driverInfo_blueprint)
    from profiles import profiles_blueprint
    app.register_blueprint(profiles_blueprint)
    app.run(debug=True)