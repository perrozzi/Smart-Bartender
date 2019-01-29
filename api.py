import os
import sys
from flask import Flask
app = Flask(__name__)

@app.route('/')
def index():
    return 'Smart-Bartender API is running!'

@app.route("/power")
def power():
    os.system("sudo shutdown -h now")

@app.route("/restart")
def restart():
    python = sys.executable
    os.execl(python, python, * sys.argv)

@app.route("/drink/<Drink>/<Action>")
def drink(Drink, Action):
    if Action == "make":
        return "Making a " + Drink
    else:
        return "Retrieving information about " + Drink

@app.route("/ingred/<Ingred>/<Action>/")
def ingred(Ingred, Action):
    if Action == "order":
        return "Ordering more " + Ingred
    elif Action[:4] == "pump":
        return "Setting " + Ingred + " to " + Action
    else:
        return "Retrieving information about " + Ingred


@app.route("/button/<Number>")
def button(Number):
    if Number == "1":
        bartender.btn1
    elif Number == "2":
        bartender.btn2
    elif Number == "3":
        bartender.btn3
    elif Number == "4":
        bartender.btn4

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')