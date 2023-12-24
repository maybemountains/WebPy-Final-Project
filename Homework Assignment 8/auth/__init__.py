from flask import Blueprint, flash, g, redirect, render_template, url_for
from flask_login import UserMixin, current_user, login_required, login_user, logout_user
from wtforms import EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired
from wtforms.validators import DataRequired, Length, Email
from flask_babel import gettext
from flask_wtf import FlaskForm
from app import bcrypt, login_manager, getSQLiteDB, app
from flask_mail import Message
import os
from dotenv import load_dotenv
from pymongo import MongoClient

auth_blueprint = Blueprint('auth', __name__,
                        template_folder='templates')


load_dotenv()

mongoClient = MongoClient(os.getenv('MONGO_URI'))

mongoDB = mongoClient['DriverCarsDB'] 
carCollection = mongoDB['carInfo']

#region user related functions & class
# creates the user class with all the necessary information
class User(UserMixin):
    def __init__(self, id, email, username, password, isDriver):
        self.id = id
        self.email = email
        self.username = username
        self.password = password
        self.isDriver = isDriver

# this function allows us to a select a user given a username
# rn just employers, can make it include regular users too later
def fetchUser(username):
    conn = getSQLiteDB()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    return User(id=user[0], username=user[1], email=user[2], password=user[3], isDriver=user[4]) if user else None

# this will check if a username has been taken
def isUsernameTaken(username):
    conn = getSQLiteDB()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    return user is not None

# this will do the inserting of the user into the table for us
def insertUser(username, email, password, isDriver):
    conn = getSQLiteDB()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, email, password, isDriver) VALUES (?, ?, ?, ?)", (username, email, bcrypt.generate_password_hash(password).decode('utf-8'), isDriver))
    conn.commit()

# this will connect to the db and get the user by id, and it will procceed to let us be able to access the user's information. I think. 
def load_user(userid):
    conn = getSQLiteDB()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (userid,))
    user = cursor.fetchone()
    if user:
        return User(id=user[0], username=user[1], email=user[2], password=None, isDriver=user[4])
    return None

#endregion

class LoginForm(FlaskForm):
    username = StringField(gettext("Username"), validators=[DataRequired(), Length(min=1, max=150)])
    password = PasswordField(gettext("Password"), validators=[DataRequired(), Length(min=8, max=300)])
    submit = SubmitField(gettext("Login"))

class RiderRegistrationForm(FlaskForm):
    username = StringField(gettext('Username'), validators=[DataRequired(), Length(min=1, max=150)])
    email = EmailField(gettext('Email'), validators=[DataRequired(), Length(min=4, max=320), Email()])
    password = PasswordField(gettext('Password'), validators=[DataRequired(), Length(min=8, max=300)])
    submit = SubmitField(gettext('Sign Up'))

class DriverRegistrationForm(FlaskForm):
    username = StringField(gettext('Username'), validators=[DataRequired(), Length(min=1, max=150)])
    email = EmailField(gettext('Email'), validators=[DataRequired(), Length(min=4, max=320), Email()])
    password = PasswordField(gettext('Password'), validators=[DataRequired(), Length(min=8, max=300)])
    licensePlate = StringField(gettext('License Plate'), validators=[DataRequired(), Length(min=4, max=320)])
    carType = StringField(gettext('Car Type'), validators=[DataRequired(), Length(min=4, max=320)])
    carColor = StringField(gettext('Car Color'), validators=[DataRequired(), Length(min=4, max=320)])
    submit = SubmitField(gettext('Sign Up'))


# this will display the signup page and do the process of signing up when a user submits the form
@auth_blueprint.route('/riderSignup', methods=['GET', 'POST'])
def riderSignup():
    # check if the user is already logged in, if so simply redirect them to the home page
    # because there's no point in having them sign up or log in otherwise (this will repeat going forward, but it always does the same thing)
    if current_user.is_authenticated:
        return redirect(url_for('welcomePage'))  # Redirect to the welcome page if already logged in
    form = RiderRegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        if not isUsernameTaken(username):
            insertUser(username, email, password, False)
            user = fetchUser(username)
            from app import gay
            msg = Message(subject="Welcome to IT Girl Transport!", body="Thank you for signing up!",
                        sender="no-reply@IT-Girl-Transport.com",
                        recipients=[user.email])
            gay.send(msg)
            login_user(user)
            return redirect('/')
        else:
            flash(gettext('Username already taken. Please choose another.'), 'danger')
    # otherwise, show the sign up form.
    return render_template('riderSignup.html', form=form)

@auth_blueprint.route('/driverSignup', methods=['GET', 'POST'])
def driverSignup():
    # check if the user is already logged in, if so simply redirect them to the home page
    # because there's no point in having them sign up or log in otherwise (this will repeat going forward, but it always does the same thing)
    if current_user.is_authenticated:
        return redirect(url_for('welcomePage'))  # Redirect to the welcome page if already logged in
    form = DriverRegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        licensePlate = form.licensePlate.data
        carColor = form.carColor.data
        carType = form.carType.data
        if not isUsernameTaken(username):
            insertUser(username, email, password, True)
            user = fetchUser(username)
            carCollection.insert_one({"carType" : carType, "carColor" : carColor, "licensePlate" : licensePlate, "driverID" : user.id}) # insert car info into mongo
            
            from app import gay
            msg = Message(subject="Welcome to IT Girl Transport!", body="Thank you for signing up to be a driver <3!",
                        sender="no-reply@IT-Girl-Transport.com",
                        recipients=[user.email])
            gay.send(msg)
            login_user(user)
            return redirect(f'/pickRide') # i dont know if this is going to work.
        else:
            flash(gettext('Username already taken. Please choose another.'), 'danger')
    # otherwise, show the sign up form.
    return render_template('driverSignup.html', form=form)


# this will display the login page and do the process of logging in when a user submits the form
@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('welcomePage'))  # Redirect to the index page if already logged in
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = fetchUser(username)
        if (username == "admin" and password == "admin123"): # if the username and password are the admin's info
            # connect to the db, select all users from the db and then send that to the admin.html as we render it
            # the admin never technically gets logged in proper but it didn't personally feel like they needed to be to me
            conn = getSQLiteDB()
            cursor = conn.cursor()
            cursor.execute("SELECT username, email, isDriver FROM users")
            users = cursor.fetchall()
            return render_template('admin.html', users=users)
        # otherwise check if the username and password match what we have in the db, and if so log them in and redirect to the index
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect('/')
        # otherwise tell the user that their login credentials are incorrect
        else:
            flash(gettext('Invalid username or password'), 'danger')
    # if no form has been submitted and the user isn't logged in, show the user the login form
    return render_template('login.html', form=form)

# a simple logout route, this just allows users to log out
@auth_blueprint.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))