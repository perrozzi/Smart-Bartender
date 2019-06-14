import time
import sys
import RPi.GPIO as GPIO
import json
import threading
import traceback
import os
import pygame
from pynput.keyboard import Key, Controller
from menu import MenuItem, Menu, Back, MenuContext, MenuDelegate

pygame.init()
keyboard = Controller()
pygame.mouse.set_visible(False)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

os.environ["SDL_FBDEV"] = "/dev/fb1"
os.environ["SDL_VIDEODRIVER"] = "fbcon"

SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480

BTN_PINS = [17, 22, 23, 27]
BTN_TEXT = ["Prev", "Select", "Next", "Back"]
BTN_STATE = [0, 0, 0, 0]
BTN_WIDTH = 140
BTN_HEIGHT = 60

NUMBER_NEOPIXELS = 45
NEOPIXEL_DATA_PIN = 26
NEOPIXEL_CLOCK_PIN = 6
NEOPIXEL_BRIGHTNESS = 64

FLOW_RATE = 60.0/100.0
HEADER_FONT = pygame.font.Font("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 28)
BUTTON_FONT = pygame.font.Font("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 22)
DETAIL_FONT = pygame.font.Font("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 18)

BLACK = (  0,   0,   0)
WHITE = (255, 255, 255)
RED =   (255,   0,   0)
GREEN = (  0, 255,   0)
BLUE =  (  0,   0, 255)
LTBLUE= (  0, 192, 240)
GREY =  (128, 128, 128)


class Bartender(MenuDelegate): 
    def __init__(self):
        self.running = False
     
        # configure interrups for buttons
        for pin in BTN_PINS:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # configure screen
        self.lcd = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.lcd.fill(WHITE)
        pygame.display.update()
        time.sleep(0.5)
        self.lcd.fill(BLACK)
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

    @staticmethod
    def readPumpConfiguration():
        return json.load(open('/home/pi/Smart-Bartender/pump_config.json'))

    @staticmethod
    def readDrinkList():
        return json.load(open('/home/pi/Smart-Bartender/drink_list.json'))

    @staticmethod
    def readDrinkOptions():
        return json.load(open('/home/pi/Smart-Bartender/drink_options.json'))

    @staticmethod
    def writePumpConfiguration(configuration):
        with open("/home/pi/Smart-Bartender/pump_config.json", "w") as jsonFile:
            json.dump(configuration, jsonFile)

    def startInterrupts(self):
        for pin in BTN_PINS:
            GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.btnPressed, bouncetime=100)

    def stopInterrupts(self):
        for pin in BTN_PINS:
            GPIO.remove_event_detect(pin)

    def drawText(self, surface, text, color, rect, font, aa=False, bkg=None):
        rect = pygame.Rect(rect)
        y = rect.top
        lineSpacing = -2
        fontHeight = font.size("Tg")[1]
        
        while text:
            i = 1

            # determine if the row of text will be outside our area
            if y + fontHeight > rect.bottom:
                break
            # determine maximum width of line
            while font.size(text[:i])[0] < rect.width and i < len(text):
                i += 1
            # if we've wrapped the text, then adjust the wrap to the last word
            if i < len(text):
                i = text.rfind(" ", 0, i) + 1
            # render the line and blit it to the surface
            if bkg:
                image = font.render(text[:i], 1, color, bkg)
                image.set_colorkey(bkg)
            else:
                image = font.render(text[:i], aa, color)

            surface.blit(image, (rect.left, y))
            y += fontHeight + lineSpacing

            # remove the text we just blitted
            text = text[i:]
            
        return text
    
    def debugText(self, text):
        self.drawText(self.lcd, text, RED, (0, SCREEN_HEIGHT-20, 400, 50), DETAIL_FONT)
        pygame.display.update()

    def drawButtons(self):
        i = 0
        for state in BTN_STATE:
            i += 1
            if state == 2:
                btnColor = GREEN
            elif state == 1:
                btnColor = BLUE
            else:
                btnColor = LTBLUE
            if (BTN_TEXT[i-1] != ""):
                pygame.draw.rect(self.lcd, btnColor, (SCREEN_WIDTH-BTN_WIDTH, (SCREEN_HEIGHT/4)*i-(BTN_HEIGHT*1.5), BTN_WIDTH, BTN_HEIGHT))
                self.lcd.blit(BUTTON_FONT.render(BTN_TEXT[i-1], True, BLACK), (SCREEN_WIDTH-BTN_WIDTH+10, (SCREEN_HEIGHT/4)*i-(BTN_HEIGHT*1.5)+10))
            else:
                pygame.draw.rect(self.lcd, BLACK, (SCREEN_WIDTH-BTN_WIDTH, (SCREEN_HEIGHT/4)*i-(BTN_HEIGHT*1.5), BTN_WIDTH, BTN_HEIGHT))
            pygame.display.update()
    
    def clearScreen(self):
        self.lcd.fill(BLACK)
        self.drawButtons()

    def buildMenu(self):
        # create a new main menu
        mm = Menu("Main Menu")
        cm = Menu("Configure")

        # add drink options
        for d in self.drink_list.keys():
            dm = Menu(self.drink_list[d]["name"])
            dm.addOption(MenuItem('drink', self.drink_list[d]['name'], {"ingredients": self.drink_list[d]['ingredients']}))
            dm.setParent(mm)
            mm.addOption(dm)

        # add pump configuration options
        pump_opts = []
        for p in sorted(self.pump_configuration.keys()):
            config = Menu(self.pump_configuration[p]["name"])
            # add fluid options for each pump
            for opt in self.drink_options.keys():
                # star the selected option
                selected = "*" if self.drink_options[opt]["value"] == self.pump_configuration[p]["value"] else ""
                config.addOption(MenuItem('pump_selection', opt, {"key": p, "value": self.drink_options[opt]["value"], "name": opt}))
            # add a back button so the user can return without modifying
            config.addOption(Back("Back"))
            config.setParent(cm)
            pump_opts.append(config)

        # add pump menus to the configuration menu
        cm.addOptions(pump_opts)
        cm.addOption(MenuItem('clean', 'Clean'))
        cm.addOption(Back("Back"))
        cm.setParent(mm)
        mm.addOption(cm)
        
        # create a menu context
        self.menuContext = MenuContext(mm, self)

    def menuItemClicked(self, menuItem):
        if (menuItem.type == "drink"):
            if BTN_STATE[1] == 2:
                self.makeDrink(menuItem.name, menuItem.attributes["ingredients"], True)
            else:
                self.makeDrink(menuItem.name, menuItem.attributes["ingredients"])
            return True
        elif(menuItem.type == "pump_selection"):
            self.pump_configuration[menuItem.attributes["key"]]["value"] = menuItem.attributes["value"]
            Bartender.writePumpConfiguration(self.pump_configuration)
            self.menuContext.back()
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
        if (menuItem.type == "drink"):
            BTN_TEXT[0] = ""
            BTN_TEXT[1] = "Confirm"
            BTN_TEXT[2] = ""
            BTN_TEXT[3] = "Back"
        elif (menuItem.type == "menu" and menuItem.name[:4] != "Pump"):
            BTN_TEXT[0] = "Prev"
            BTN_TEXT[1] = "Select"
            BTN_TEXT[2] = "Next"
            BTN_TEXT[3] = ""
        else:
            BTN_TEXT[0] = "Prev"
            BTN_TEXT[1] = "Select"
            BTN_TEXT[2] = "Next"
            BTN_TEXT[3] = "Back"
        self.clearScreen()
        self.drawText(self.lcd, menuItem.name, WHITE, (20, 60, 400, 300), HEADER_FONT)
        
        if (menuItem.type == "drink"):
            # Drink confirm menu
            self.clearScreen()
            self.drawButtons()
            i = 0
            pumps = []
            ings = []
            ing_loaded = []
            ing_manual = []
            
            self.drawText(self.lcd, menuItem.name, WHITE, (170, 60, 300, 300), HEADER_FONT)
            if (self.drink_list[menuItem.name]["image"] != ""):
                pic = pygame.image.load(self.drink_list[menuItem.name]["image"])
                pic = pygame.transform.scale(pic, (150, 150))
                self.lcd.blit(pic, (0, 0))
            
            for p in self.pump_configuration.keys():
                pumps.append(self.pump_configuration[p]["value"])
            for ing in self.drink_list[menuItem.name]["ingredients"]:
                for o in self.drink_options.keys():
                    if (ing in pumps) and (ing == self.drink_options[o]["value"]):
                        ing_loaded.append(self.drink_options[o]["name"])
                    elif (ing == self.drink_options[o]["value"]):
                        ing_manual.append(self.drink_options[o]["name"])
            if ing_loaded:
                for ing in ing_loaded:
                    i += 1
                    self.drawText(self.lcd, ing, WHITE, (40, 150+(i*20), 600, 200), DETAIL_FONT)
            i += 2
            if ing_manual:
                self.drawText(self.lcd, "MANUALLY ADD:", WHITE, (30, 150+(i*20), 600, 200), DETAIL_FONT)
                for ing in ing_manual:
                    i += 1
                    self.drawText(self.lcd, ing, WHITE, (40, 150+(i*20), 400, 300), DETAIL_FONT)
            i += 2
            self.drawText(self.lcd, 'Preparation: '+ self.drink_list[menuItem.name]["preparation"], WHITE, (40, 150+(i*20), 400, 100), DETAIL_FONT)
            self.drawText(self.lcd, 'Served in: ' + self.drink_list[menuItem.name]["drinkware"], WHITE, (40, SCREEN_HEIGHT-50, 400, 50), DETAIL_FONT)
            self.drawText(self.lcd, 'Hold 2 secs for a Double', LTBLUE, (SCREEN_WIDTH-140, SCREEN_HEIGHT-265, 130, 200), DETAIL_FONT)
        elif (menuItem.type == "menu"):
            if (menuItem.name[:4] == "Pump"):
                for p in self.pump_configuration.keys():
                    if (self.pump_configuration[p]["name"] == menuItem.name):
                        for o in self.drink_options.keys():
                            if (self.pump_configuration[p]["value"] == self.drink_options[o]["value"]):
                                self.drawText(self.lcd, self.drink_options[o]["name"], WHITE, (40, 120, 400, 600), DETAIL_FONT)
            elif (menuItem.name != "Configure"):
                # Drink select menu
                ingredients = self.drink_list[menuItem.name]["ingredients"]
                presentIng = 0
                for ing in ingredients.keys():
                    for p in self.pump_configuration.keys():
                        if (ing == self.pump_configuration[p]["value"]):
                            presentIng += 1
                if (presentIng == len(ingredients.keys())): 
                    textColor = WHITE
                else:
                    textColor = GREY
                    self.drawText(self.lcd, '(not all ingredients present)', textColor, (20, 90, 400, 200), DETAIL_FONT)
                
                self.drawText(self.lcd, self.drink_list[menuItem.name]["description"], textColor, (40, 120, 400, 600), DETAIL_FONT)
                self.drawText(self.lcd, 'Preparation: '+ self.drink_list[menuItem.name]["preparation"], textColor, (40, SCREEN_HEIGHT-150, 400, 100), DETAIL_FONT)
                self.drawText(self.lcd, 'Served in: ' + self.drink_list[menuItem.name]["drinkware"], textColor, (40, SCREEN_HEIGHT-50, 400, 50), DETAIL_FONT)
        elif (menuItem.type == "pump_selection"):
            self.drawText(self.lcd, self.drink_options[menuItem.name]["description"], WHITE, (40, 120, 400, 600), DETAIL_FONT)
            self.drawText(self.lcd, 'Type: '+ self.drink_options[menuItem.name]["type"], WHITE, (40, SCREEN_HEIGHT-50, 400, 100), DETAIL_FONT)
        
        pygame.display.update()

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
            self.updateProgressBar(x, y=20)
            pygame.display.update()
            time.sleep(interval)

    def makeDrink(self, drink, ingredients, double=False):
        # cancel any button presses while the drink is being made
        self.stopInterrupts()
        self.running = True

        # launch a thread to control lighting
        #lightsThread = threading.Thread(target=self.cycleLights)
        #lightsThread.start()

        # Parse the drink ingredients and spawn threads for pumps
        maxTime = 0
        pumpThreads = []
        for ing in ingredients.keys():
            for pump in self.pump_configuration.keys():
                if ing == self.pump_configuration[pump]["value"]:
                    if double:
                        # TODO: Shouldn't a double only be twice the liquor and not the mixers?
                        waitTime = ingredients[ing] * 2 * FLOW_RATE
                    else:
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
        #lightsThread.do_run = False
        #lightsThread.join()

        # show the ending sequence lights
        #self.lightsEndingSequence()

        # sleep for a couple seconds to make sure the interrupts don't get triggered
        time.sleep(2);

        # reenable interrupts
        self.startInterrupts()
        self.running = False

    def btnPressed(self, ctx):
        if (ctx == 17):
            if (GPIO.input(ctx)):
                print("input")
                keyboard.press(Key.up)
            else:
                print("no input")
                keyboard.release(Key.up)
        elif (ctx == 22):
            if (GPIO.input(ctx)):
                keyboard.press(Key.right)
            else:
                keyboard.release(Key.right)
        elif (ctx == 23):
            if (GPIO.input(ctx)):
                keyboard.press(Key.down)
            else:
                keyboard.release(Key.down)
        elif (ctx == 27):
            if (GPIO.input(ctx)):
                keyboard.press(Key.left)
            else:
                keyboard.release(Key.left)

    def updateProgressBar(self, percent, x=170, y=15):
        height = 20
        width = SCREEN_WIDTH - 2 * x
        for w in range(0, width):
            self.lcd.set_at((w + x, y), GREEN)
            self.lcd.set_at((w + x, y + height), GREEN)
        for h in range(0, height):
            self.lcd.set_at((x, h + y), GREEN)
            self.lcd.set_at((SCREEN_WIDTH - x, h + y), GREEN)
            for p in range(0, percent):
                p_loc = int(p/100.0*width)
                self.lcd.set_at((x + p_loc, h + y), GREEN)
                
    def processInput(self):
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                print("keydown")
                self.start_time = time.time()
            if event.type == pygame.KEYUP:
                self.hold_time = time.time() - self.start_time
                if event.key == pygame.K_UP:
                    print(self.hold_time)
                    if self.hold_time >= 2:
                        BTN_STATE[0] = 2
                    else:
                        BTN_STATE[0] = 1
                    self.drawButtons()
                    time.sleep(0.2)
                    self.menuContext.prev()
                    BTN_STATE[0] = 0
                    self.drawButtons()
                elif event.key == pygame.K_RIGHT:
                    print(self.hold_time)
                    if self.hold_time >= 2:
                        BTN_STATE[1] = 2
                    else:
                        BTN_STATE[1] = 1
                    self.drawButtons()
                    time.sleep(0.2)
                    self.menuContext.select()
                    BTN_STATE[1] = 0
                    self.drawButtons()
                elif event.key == pygame.K_DOWN:
                    print(self.hold_time)
                    if self.hold_time >= 2:
                        BTN_STATE[2] = 2
                    else:
                        BTN_STATE[2] = 1
                    self.drawButtons()
                    time.sleep(0.2)
                    self.menuContext.next()
                    BTN_STATE[2] = 0
                    self.drawButtons()
                elif event.key == pygame.K_LEFT:
                    print(self.hold_time)
                    if self.hold_time >= 2:
                        BTN_STATE[3] = 2
                    else:
                        BTN_STATE[3] = 1
                    self.drawButtons()
                    time.sleep(0.2)
                    self.menuContext.back()
                    BTN_STATE[3] = 0
                    self.drawButtons()

    def run(self):
        self.startInterrupts()
        self.drawButtons()
        # main loop
        try:
            while True:
                self.processInput()                
                time.sleep(0.1)
          
        except KeyboardInterrupt:  
            print ("Keyboard interrupt")
        
        except:
            print ("some error")
        
        finally:
            print ("clean up")
            GPIO.cleanup()           # clean up GPIO on normal exit
            traceback.print_exc()

bartender = Bartender()
bartender.buildMenu()
bartender.run()