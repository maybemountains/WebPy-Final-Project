import os
from bson import ObjectId
from dotenv import load_dotenv
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from pymongo import MongoClient
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from wtforms.validators import DataRequired, Length
from flask_babel import gettext
from flask_wtf import FlaskForm
from app import getSQLiteDB

driverInfo_blueprint = Blueprint('driverInfo', __name__,
                        template_folder='templates')

load_dotenv()

mongoClient = MongoClient(os.getenv('MONGO_URI'))

mongoDB = mongoClient['DriverCarsDB'] 
carCollection = mongoDB['carInfo']

@driverInfo_blueprint.route('/deleteDriverInfo')
@login_required
def deleteInfo():
    driverId = int(current_user.id)
    car = carCollection.find_one({"driverID": driverId}) # find a car attached to our driver
    if not (car is None): # if there was a car, delete that car
        carCollection.delete_one({"driverID": driverId})
    return redirect('/profile') # otherwise just redirect to their profile again (aka do nothing)


@driverInfo_blueprint.route('/editDriver', methods=['GET', 'POST'])
@login_required
def editDriver():
    driverId = int(current_user.id)
    car = carCollection.find_one({"driverID": driverId}) # find a car attached to the driver

    if (car): # if there's a car attached, make sure the form has the data already filled in so they user can decide what they're changing without having to 
              # rewrite everything from scratch
        form = carForm(data={'carType': car['carType'], 'carColor': car['carColor'], 'licensePlate': car['licensePlate']})
    else: # otherwise, meaning they deleted their car info, fill in the form with empty lines so that we can properly render the form
        form = carForm(data={'carType': '', 'carColor': '', 'licensePlate': ''})
    
    if form.validate_on_submit():
        carType = form.carType.data.lower()
        carColor = form.carColor.data
        licensePlate = form.licensePlate.data
        # if there's a car already there we're updating the info otherwise we're creating a new entry so that there's now a car
        if (car): 
            carCollection.find_one_and_update({"driverID" : driverId}, {"$set" : {'carType': carType, 'carColor': carColor, 'licensePlate': licensePlate}})
            # carCollection.update_one({"driverID": driverId}, {'$set': {'carType': carType, 'carColor': carColor, 'licensePlate': licensePlate}})
        else:  # otherwise if we didn't already have a car, just insert a new entry into the db
            carCollection.insert_one({'carType': carType, 'carColor': carColor, 'licensePlate': licensePlate, "driverID": driverId})
        flash(gettext("you edited your car information"))
        return redirect('/profile')
    return render_template('editDriver.html', form=form, edit=True)

class carForm(FlaskForm):
    licensePlate = StringField(gettext('License Plate'), validators=[DataRequired(), Length(min=4, max=320)])
    carType = StringField(gettext('Car Type'), validators=[DataRequired(), Length(min=4, max=320)])
    carColor = StringField(gettext('Car Color'), validators=[DataRequired(), Length(min=4, max=320)])
    submit = SubmitField(gettext('Save'))
