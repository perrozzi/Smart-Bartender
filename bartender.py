import time
import sys
import RPi.GPIO as GPIO
import json
import threading
import traceback
import os
import pygame

from menu import MenuItem, Menu, Back, MenuContext, MenuDelegate

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

os.environ["SDL_FBDEV"] = "/dev/fb1"
os.environ["SDL_VIDEODRIVER"] = "fbcon"

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

OLED_RESET_PIN = 24
OLED_DC_PIN = 22

NUMBER_NEOPIXELS = 45
NEOPIXEL_DATA_PIN = 26
NEOPIXEL_CLOCK_PIN = 6
NEOPIXEL_BRIGHTNESS = 64

FLOW_RATE = 60.0/100.0

class Bartender(MenuDelegate): 
    def __init__(self):
        self.running = False

        # set the oled screen height
        self.screen_width = SCREEN_WIDTH
        self.screen_height = SCREEN_HEIGHT
     
        # configure interrups for buttons
        GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # configure screen
        self.lcd = pygame.display.set_mode((320, 240))
        self.lcd.fill((255,255,255))
        pygame.display.update()
        self.lcd.fill((0,0,0))
        pygame.display.update()
        time.sleep(0.5)

        # load the pump configuration from file
        self.pump_configuration = Bartender.readPumpConfiguration()
        for pump in self.pump_configuration.keys():
            GPIO.setup(self.pump_configuration[pump]["pin"], GPIO.OUT, initial=GPIO.HIGH)

        # load the drink and ingredient configurations
        self.drink_list = Bartender.readDrinkList()
        self.drink_options = Bartender.readDrinkOptions()

        # setup pixels:
        self.numpixels = NUMBER_NEOPIXELS

        # Here's how to control the strip from any two GPIO pins:
        #datapin  = NEOPIXEL_DATA_PIN
        #clockpin = NEOPIXEL_CLOCK_PIN
        #self.strip = Adafruit_DotStar(self.numpixels, datapin, clockpin)
        #self.strip.begin()           # Initialize pins for output
        #self.strip.setBrightness(NEOPIXEL_BRIGHTNESS) # Limit brightness to ~1/4 duty cycle

        # turn everything off
        #for i in range(0, self.numpixels):
        #    self.strip.setPixelColor(i, 0)
        #self.strip.show() 

        print ("Done initializing")

    @staticmethod
    def readPumpConfiguration():
        return json.load(open('pump_config.json'))

    @staticmethod
    def readDrinkList():
        return json.load(open('drink_list.json'))

    @staticmethod
    def readDrinkOptions():
        return json.load(open('drink_options.json'))

    @staticmethod
    def writePumpConfiguration(configuration):
        with open("pump_config.json", "w") as jsonFile:
            json.dump(configuration, jsonFile)

    def startInterrupts(self):
        GPIO.add_event_detect(17, GPIO.FALLING, callback=self.btn1, bouncetime=1000)
        GPIO.add_event_detect(22, GPIO.FALLING, callback=self.btn2, bouncetime=1000)
        GPIO.add_event_detect(23, GPIO.FALLING, callback=self.btn3, bouncetime=1000)
        GPIO.add_event_detect(27, GPIO.FALLING, callback=self.btn4, bouncetime=1000)

    def stopInterrupts(self):
        GPIO.remove_event_detect(17)
        GPIO.remove_event_detect(22)
        GPIO.remove_event_detect(23)
        GPIO.remove_event_detect(27)

    def buildMenu(self):
        # create a new main menu
        m = Menu("Main Menu")

        # add drink options
        drink_opts = []
        for d in self.drink_list.keys():
            drink_opts.append(MenuItem('drink', self.drink_list[d]['description'], {"ingredients": self.drink_list[d]['ingredients']}))

        configuration_menu = Menu("Configure")

        # add pump configuration options
        pump_opts = []
        for p in sorted(self.pump_configuration.keys()):
            config = Menu(self.pump_configuration[p]["name"])
            # add fluid options for each pump
            for opt in self.drink_options.keys():
                # star the selected option
                selected = "*" if self.drink_options[opt] == self.pump_configuration[p]["value"] else ""
                config.addOption(MenuItem('pump_selection', self.drink_options[opt]["name"], {"key": p, "value": opt, "name": self.drink_options[opt]["name"]}))
            # add a back button so the user can return without modifying
            config.addOption(Back("Back"))
            config.setParent(configuration_menu)
            pump_opts.append(config)

        # add pump menus to the configuration menu
        configuration_menu.addOptions(pump_opts)
        # add a back button to the configuration menu
        configuration_menu.addOption(Back("Back"))
        # adds an option that cleans all pumps to the configuration menu
        configuration_menu.addOption(MenuItem('clean', 'Clean'))
        configuration_menu.setParent(m)

        m.addOptions(drink_opts)
        m.addOption(configuration_menu)
        # create a menu context
        self.menuContext = MenuContext(m, self)

    def filterDrinks(self, menu):
        """
        Removes any drinks that can't be handled by the pump configuration
        """
        for i in menu.options:
            if (i.type == "drink"):
                i.visible = False
                ingredients = i.attributes["ingredients"]
                presentIng = 0
                for ing in ingredients.keys():
                    for p in self.pump_configuration.keys():
                        if (ing == self.pump_configuration[p]["value"]):
                            presentIng += 1
                if (presentIng == len(ingredients.keys())): 
                    i.visible = True
            elif (i.type == "menu"):
                self.filterDrinks(i)

    def selectConfigurations(self, menu):
        """
        Adds a selection star to the pump configuration option
        """
        for i in menu.options:
            if (i.type == "pump_selection"):
                key = i.attributes["key"]
                if (self.pump_configuration[key]["value"] == i.attributes["value"]):
                    i.name = "%s %s" % (i.attributes["name"], "*")
                else:
                    i.name = i.attributes["name"]
            elif (i.type == "menu"):
                self.selectConfigurations(i)

    def prepareForRender(self, menu):
        self.filterDrinks(menu)
        self.selectConfigurations(menu)
        return True

    def menuItemClicked(self, menuItem):
        if (menuItem.type == "drink"):
            self.makeDrink(menuItem.name, menuItem.attributes["ingredients"])
            return True
        elif(menuItem.type == "pump_selection"):
            self.pump_configuration[menuItem.attributes["key"]]["value"] = menuItem.attributes["value"]
            Bartender.writePumpConfiguration(self.pump_configuration)
            return True
        elif(menuItem.type == "clean"):
            self.clean()
            return True
        return False

    def clean(self):
        waitTime = 20
        pumpThreads = []

        # cancel any button presses while the drink is being made
        # self.stopInterrupts()
        self.running = True

        for pump in self.pump_configuration.keys():
            pump_t = threading.Thread(target=self.pour, args=(self.pump_configuration[pump]["pin"], waitTime))
            pumpThreads.append(pump_t)

        # start the pump threads
        for thread in pumpThreads:
            thread.start()

        # start the progress bar
        self.progressBar(waitTime)

        # wait for threads to finish
        for thread in pumpThreads:
            thread.join()

        # show the main menu
        self.menuContext.showMenu()

        # sleep for a couple seconds to make sure the interrupts don't get triggered
        time.sleep(2);

        # reenable interrupts
        # self.startInterrupts()
        self.running = False

    def displayMenuItem(self, menuItem):
        print (menuItem.name)
        self.led.clear_display()
        self.led.draw_text2(0,20,menuItem.name,2)
        self.led.display()

    def cycleLights(self):
        t = threading.currentThread()
        head  = 0               # Index of first 'on' pixel
        tail  = -10             # Index of last 'off' pixel
        color = 0xFF0000        # 'On' color (starts red)

        while getattr(t, "do_run", True):
            self.strip.setPixelColor(head, color) # Turn on 'head' pixel
            self.strip.setPixelColor(tail, 0)     # Turn off 'tail'
            self.strip.show()                     # Refresh strip
            time.sleep(1.0 / 50)             # Pause 20 milliseconds (~50 fps)

            head += 1                        # Advance head position
            if(head >= self.numpixels):           # Off end of strip?
                head    = 0              # Reset to start
                color >>= 8              # Red->green->blue->black
                if(color == 0): color = 0xFF0000 # If black, reset to red

            tail += 1                        # Advance tail position
            if(tail >= self.numpixels): tail = 0  # Off end? Reset

    def lightsEndingSequence(self):
        # make lights green
        for i in range(0, self.numpixels):
            self.strip.setPixelColor(i, 0xFF0000)
        self.strip.show()

        time.sleep(5)

        # turn lights off
        for i in range(0, self.numpixels):
            self.strip.setPixelColor(i, 0)
        self.strip.show() 

    def pour(self, pin, waitTime):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(waitTime)
        GPIO.output(pin, GPIO.HIGH)

    def progressBar(self, waitTime):
        interval = waitTime / 100.0
        for x in range(1, 101):
            self.led.clear_display()
            self.updateProgressBar(x, y=35)
            self.led.display()
            time.sleep(interval)

    def makeDrink(self, drink, ingredients):
        # cancel any button presses while the drink is being made
        # self.stopInterrupts()
        self.running = True

        # launch a thread to control lighting
        lightsThread = threading.Thread(target=self.cycleLights)
        lightsThread.start()

        # Parse the drink ingredients and spawn threads for pumps
        maxTime = 0
        pumpThreads = []
        for ing in ingredients.keys():
            for pump in self.pump_configuration.keys():
                if ing == self.pump_configuration[pump]["value"]:
                    waitTime = ingredients[ing] * FLOW_RATE
                    if (waitTime > maxTime):
                        maxTime = waitTime
                    pump_t = threading.Thread(target=self.pour, args=(self.pump_configuration[pump]["pin"], waitTime))
                    pumpThreads.append(pump_t)

        # start the pump threads
        for thread in pumpThreads:
            thread.start()

        # start the progress bar
        self.progressBar(maxTime)

        # wait for threads to finish
        for thread in pumpThreads:
            thread.join()

        # show the main menu
        self.menuContext.showMenu()

        # stop the light thread
        lightsThread.do_run = False
        lightsThread.join()

        # show the ending sequence lights
        self.lightsEndingSequence()

        # sleep for a couple seconds to make sure the interrupts don't get triggered
        time.sleep(2);

        # reenable interrupts
        # self.startInterrupts()
        self.running = False

    def btn1(self, ctx):
        if not self.running:
            global btn1Time
            start_time = time.time()

            while GPIO.input(ctx) == 0: # Wait for the button up
                pass

            btn1Time = time.time() - start_time    # How long was the button down?

            if btn1Time >= .1:
                # short press
                self.menuContext.prev()
            if btn1Time >= 3:
                # long press
                self.menuContext.prev()

    def btn2(self, ctx):
        if not self.running:
            global btn2Time
            start_time = time.time()

            while GPIO.input(ctx) == 0: # Wait for the button up
                pass

            btn2Time = time.time() - start_time    # How long was the button down?

            if btn2Time >= .1:
                # short press
                self.menuContext.select()
            if btn2Time >= 3:
                # long press
                self.menuContext.select()

    def btn3(self, ctx):
        if not self.running:
            global btn3Time
            start_time = time.time()

            while GPIO.input(ctx) == 0: # Wait for the button up
                pass

            btn3Time = time.time() - start_time    # How long was the button down?

            if btn3Time >= .1:
                # short press
                self.menuContext.next()
            if btn3Time >= 3:
                # long press
                self.menuContext.next()

    def btn4(self, ctx):
        if not self.running:
            global btn4Time
            start_time = time.time()

            while GPIO.input(ctx) == 0: # Wait for the button up
                pass

            btn4Time = time.time() - start_time    # How long was the button down?

            if btn4Time >= .1:
                # short press
                self.menuContext.back()
            if btn4Time >= 3:
                # long press
                os.system("sudo shutdown -h now")


    def updateProgressBar(self, percent, x=15, y=15):
        height = 10
        width = self.screen_width-2*x
        for w in range(0, width):
            self.led.draw_pixel(w + x, y)
            self.led.draw_pixel(w + x, y + height)
        for h in range(0, height):
            self.led.draw_pixel(x, h + y)
            self.led.draw_pixel(self.screen_width-x, h + y)
            for p in range(0, percent):
                p_loc = int(p/100.0*width)
                self.led.draw_pixel(x + p_loc, h + y)

    def run(self):
        self.startInterrupts()
        # main loop
        try:  
            while True:
                time.sleep(0.1)
          
        except KeyboardInterrupt:  
            GPIO.cleanup()       # clean up GPIO on CTRL+C exit  
        GPIO.cleanup()           # clean up GPIO on normal exit 

        traceback.print_exc()


bartender = Bartender()
bartender.buildMenu()
bartender.run()