import os
from dotenv import load_dotenv
from flask import Blueprint, redirect, render_template
from flask_login import current_user, login_required
from pymongo import MongoClient
 
load_dotenv()

mongoClient = MongoClient(os.getenv('MONGO_URI'))

mongoDB = mongoClient['DriverCarsDB'] 
carCollection = mongoDB['carInfo']

profiles_blueprint = Blueprint('profiles', __name__,
                        template_folder='templates')

@profiles_blueprint.route('/profile')
@login_required
def profile(): # make sure to only ever render the current user's car information
    car = carCollection.find_one({"driverID": int(current_user.id)})
    return render_template('profile.html', car=car)