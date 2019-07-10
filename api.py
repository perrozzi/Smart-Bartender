import os
import sys
import json
import time
import threading
import traceback
import RPi.GPIO as GPIO
from flask import Flask, request, jsonify, abort, render_template
app = Flask(__name__)

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
RUNNING = False

drink_list = json.load(open('/home/pi/Smart-Bartender/drinks.json'))
ingred_list = json.load(open('/home/pi/Smart-Bartender/ingreds.json'))
pump_list = json.load(open('/home/pi/Smart-Bartender/pumps.json'))
settings = json.load(open('/home/pi/Smart-Bartender/settings.json'))

for pumps in pump_list:
    GPIO.setup(pumps['value'], GPIO.OUT, initial=GPIO.HIGH)

def pour(pin, waitTime):
    #GPIO.output(pin, GPIO.LOW)
    time.sleep(waitTime)
    #GPIO.output(pin, GPIO.HIGH)

@app.route('/')
def index():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/power")
def power():
    os.system("sudo shutdown -h now")

@app.route("/restart")
def restart():
    python = sys.executable
    os.execl(python, python, * sys.argv)

@app.route("/settings")
def listSettings():
    return jsonify(settings)

@app.route("/setting/<setting_val>")
def showSetting(setting_val):
    setting = [setting for setting in settings if setting['value'] == setting_val]
    return jsonify([setting[0]])

def getSetting(setting_val):
    setting = [setting for setting in settings if setting['value'] == setting_val]
    return setting[0]["set"]
    
@app.route("/drinks")
def listDrinks():
    return jsonify(drink_list)

@app.route('/drink/<drink_val>', methods=['GET'])
def showDrink(drink_val):
    drink = [drink for drink in drink_list if drink['value'] == drink_val]
    if len(drink) == 0:
        abort(404)
    return jsonify([drink[0]])

@app.route('/drink/make/time/<drink_val>', methods=['GET'])
def calcMakeTime(drink_val):
    waitTime = 0
    # use for any modifier, such as "double"
    modifier = request.args.get('modifier')
    for ingreds in showDrinkIngreds(drink_val):
        if getSetting("similar") == "Yes" and 'value-similar' in ingreds:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value-similar']]
        if getSetting("related") == "Yes" and 'value-related' in ingreds:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value-related']]
        try: pump
        except NameError: pump = None
        if pump is None or len(pump) == 0:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value']]
        if len(pump) > 0 and ingreds['value'] <> "garnish":
            if ingreds['unit'] == "cl":
                if ingreds['amount'] * 10 * float(getSetting("flow")) > waitTime:
                    waitTime = ingreds['amount'] * 10 * float(getSetting("flow"))
            elif ingreds['unit'] == "ml":
                if ingreds['amount'] * float(getSetting("flow")) > waitTime:
                    waitTime = ingreds['amount'] * float(getSetting("flow"))
            if modifier == "double" and waitTime * 2 > waitTime:
                waitTime = waitTime * 2
    return str(waitTime)

@app.route('/drink/make/<drink_val>', methods=['GET'])
def makeDrink(drink_val):
    pumpThreads = []
    # use for any modifier, such as "double"
    modifier = request.args.get('modifier')
    for ingreds in showDrinkIngreds(drink_val):
        if getSetting("similar") == "Yes" and 'value-similar' in ingreds:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value-similar']]
        if getSetting("related") == "Yes" and 'value-related' in ingreds:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value-related']]
        try: pump
        except NameError: pump = None
        if pump is None or len(pump) == 0:
            pump = [pump for pump in pump_list if pump['description'] == ingreds['value']]
        if len(pump) > 0 and ingreds['value'] <> "garnish":
            if ingreds['unit'] == "cl":
                waitTime = ingreds['amount'] * 10 * float(getSetting("flow"))
            elif ingreds['unit'] == "ml":
                waitTime = ingreds['amount'] * float(getSetting("flow"))
            if modifier == "double":
                waitTime = waitTime * 2
            pump_t = threading.Thread(target=pour, args=(pump[0]['value'], waitTime))
            pumpThreads.append(pump_t)
            ingreds["pumped"] = True
            ingreds["time"] = waitTime
        else:
            ingreds["pumped"] = False

    RUNNING = True
    # start the pump threads
    for thread in pumpThreads:
        thread.start()
    # wait for threads to finish
    for thread in pumpThreads:
        thread.join()
    RUNNING = False
    return jsonify(showDrinkIngreds(drink_val))

@app.route('/drink/add', methods=['POST'])
def addDrink():
    if not request.json or not 'name' in request.json:
        abort(400)
    drink = {
        'value': drinks[-1]['value'] + 1,
        'name': request.json['name'],
        'description': request.json.get('description', ""),
        'prepartion': request.json.get('preparation', ""),
        'drinkware': request.json.get('drinkware', ""),
        'image': request.json.get('image', ""),
        'ingredients': request.json.get('ingredients', ""),
    }
    drink_list.append(drink)
    return jsonify({'drink': drink}), 201

@app.route('/drink/update/<drink_val>', methods=['PUT'])
def updateDrink(drink_val):
    drink = [drink for drink in drink_list if drink['value'] == drink_val]
    if len(drink) == 0:
        abort(404)
    if not request.json:
        abort(400)
    if 'name' in request.json and type(request.json['name']) != unicode:
        abort(400)
    if 'description' in request.json and type(request.json['description']) is not unicode:
        abort(400)
    if 'preparation' in request.json and type(request.json['preparation']) is not unicode:
        abort(400)
    drink[0]['name'] = request.json.get('name', drink[0]['name'])
    drink[0]['description'] = request.json.get('description', drink[0]['description'])
    drink[0]['preparation'] = request.json.get('preparation', drink[0]['preparation'])
    return jsonify({'drink': drink[0]})

@app.route('/drink/delete/<drink_val>', methods=['DELETE'])
def deleteDrink(drink_val):
    drink = [drink for drink in drink_list if drink['value'] == drink_val]
    if len(drink) == 0:
        abort(404)
    drink_list.remove(drink[0])
    return jsonify({'result': True})

@app.route('/drink/ingreds/<drink_val>', methods=['GET'])
def showDrinkIngreds(drink_val):
    drink = [drink for drink in drink_list if drink['value'] == drink_val]
    for ingreds in drink[0]['ingredients']:
        pump = [pump for pump in pump_list if pump['description'] == ingreds['value']]
        if len(pump) > 0:
            ingreds['pump'] = pump[0]['value']
        # check and see if any of the related/similar ingredients are loaded on a pump
        ingred = [ingred for ingred in ingred_list if ingred['value'] == ingreds['value']]
        if len(ingred) > 0 and getSetting("related") == "Yes" and 'related' in ingred[0]:
            # if there's only one related drink
            pump_related = [pump_related for pump_related in pump_list if pump_related['description'] == ingred[0]['related']]
            if len(pump_related) > 0:
                ingreds['pump-related'] = pump_related[0]['value']
                ingreds['value-related'] = ingred[0]['related']
            # if there's a list of related drinks
            for ingreds_related in ingred[0]['related']:
                pump_related = [pump_related for pump_related in pump_list if pump_related['description'] == ingreds_related]
                if len(pump_related) > 0:
                    ingreds['pump-related'] = pump_related[0]['value']
                    ingreds['value-related'] = ingreds_related
        if len(ingred) > 0 and getSetting("similar") == "Yes" and 'similar' in ingred[0]:
            # if there's only one similar drink
            pump_similar = [pump_similar for pump_similar in pump_list if pump_similar['description'] == ingred[0]['similar']]
            if len(pump_similar) > 0:
                ingreds['pump-similar'] = pump_similar[0]['value']
                ingreds['value-similar'] = ingred[0]['similar']
            # if there's a list of similar drinks
            for ingreds_similar in ingred[0]['similar']:
                pump_similar = [pump_similar for pump_similar in pump_list if pump_similar['description'] == ingreds_similar]
                if len(pump_similar) > 0:
                    ingreds['pump-similar'] = pump_similar[0]['value']
                    ingreds['value-similar'] = ingreds_similar

    if request.args.get('json') == "true":
        return jsonify(drink[0]['ingredients'])
    else:
        return drink[0]['ingredients']

@app.route('/drink/character/<drink_val>', methods=['GET'])
def calcDrinkCharacter(drink_val):
    alcohol = 0
    acid = 0
    bitter = 0
    sweet = 0
    volume = 0
    tot_vol = 0
    abv = 0
    character = []
    drink = [drink for drink in drink_list if drink['value'] == drink_val]
    for ingreds in drink[0]['ingredients']:
        for attribute, value in ingreds.items():
            if (attribute == "amount"):
                volume = value
                tot_vol = tot_vol + value
            if (attribute == "value" and value != "garnish"):
                ingred = [ingred for ingred in ingred_list if ingred['value'] == value]
                alcohol = alcohol + ((ingred[0]['abv'] * volume) / 100)
                acid = acid + (ingred[0]['acid'] * volume)
                sweet = sweet + (ingred[0]['sweet'] * volume)
                bitter = bitter + (ingred[0]['bitter'] * volume)
    abv = (alcohol / tot_vol) * 100
    balance = (sweet - acid * 10)
    bitter = (bitter - sweet - acid * 10)
    if (abv >= 20):
        character.append("boozy")
    if (balance < -20):
        character.append("acidic")
    elif (balance > 20):
        charcter.append("sweet")
    else:
        character.append("balanced")
    if (bitter >= 20):
        character.append("bitter")
    return jsonify({'character': character, 'alcohol': alcohol, 'abv': abv, 'acid': acid, 'sweet': sweet, 'bitter': bitter, 'balance': balance, 'tot_vol': tot_vol})

@app.route("/ingreds")
def listIngreds():
    return jsonify(ingred_list)

@app.route('/ingred/<ingred_val>', methods=['GET'])
def showIngred(ingred_val):
    ingred = [ingred for ingred in ingred_list if ingred['value'] == ingred_val]
    if len(ingred) == 0:
        abort(404)
    return jsonify([ingred[0]])

@app.route('/ingred/pump/<ingred_val>', methods=['GET'])
def showIngredPump(ingred_val):
    pump = [pump for pump in pump_list if pump['description'] == ingred_val]
    if len(pump) == 0:
        abort(404)
    return jsonify([pump[0]])

@app.route("/pumps")
def listPumps():
    return jsonify(pump_list)

@app.route('/pump/<int:pump_val>', methods=['GET'])
def showPump(pump_val):
    pump = [pump for pump in pump_list if pump['value'] == pump_val]
    if len(pump) == 0:
        abort(404)
    return jsonify([pump[0]])

@app.route('/pump/update/<int:pump_val>', methods=['PUT', 'POST'])
def updatePump(pump_val):
    pump = [pump for pump in pump_list if pump['value'] == pump_val]
    if len(pump) == 0:
        abort(404)
    if not request.json:
        abort(400)
    if 'description' in request.json and type(request.json['description']) != unicode:
        abort(400)
    pump[0]['description'] = request.json.get('description', pump[0]['description'])
    json.dump(pump_list, open('/home/pi/Smart-Bartender/pump_config.json', 'w'))
    return jsonify([pump[0]])

@app.route('/pin/<int:pin>/<int:waitTime>', methods=['GET'])
def triggerPin(pin, waitTime):
    GPIO.output(pin, GPIO.LOW)
    time.sleep(waitTime)
    GPIO.output(pin, GPIO.HIGH)

if __name__ == '__main__':
    app.run(debug=True, port=80, host='0.0.0.0')