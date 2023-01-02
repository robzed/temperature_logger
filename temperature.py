from machine import Pin, I2C, SPI, ADC
import time
import sdcard	# to get this onto the Pico, Select "Save copy..." on module files, chose "Raspberry Pi Pico" and entered the filename manually.
import os

import array
from rp2 import PIO, StateMachine, asm_pio


# --------------------------------------------------------------
# RGB LED code
# From: https://github.com/CytronTechnologies/MAKER-PI-PICO/blob/main/Example%20Code/MicroPython/maker-pi-pico-rgb-led.py
# (MIT License)
# Configure the number of WS2812 LEDs
# - There's 1x built-in RGB LED on Maker Pi Pico board
NUM_LEDS = 1

@asm_pio(sideset_init=PIO.OUT_LOW, out_shiftdir=PIO.SHIFT_LEFT,
autopull=True, pull_thresh=24)
def ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    label("bitloop")
    out(x, 1) .side(0) [T3 - 1]
    jmp(not_x, "do_zero") .side(1) [T1 - 1]
    jmp("bitloop") .side(1) [T2 - 1]
    label("do_zero")
    nop() .side(0) [T2 - 1]

# Create the StateMachine with the ws2812 program, outputting on pin GP28 (Maker Pi Pico).
sm = StateMachine(0, ws2812, freq=8000000, sideset_base=Pin(28))

# Start the StateMachine, it will wait for data on its FIFO.
sm.active(1)

# Display a pattern on the LEDs via an array of LED RGB values.
np = array.array("I", [0 for _ in range(NUM_LEDS)])

# --------------------------------------------------------------
# Main ADC code

adc_conversion_factor = 3.3 / (65535)
terminal_pull_up_resistor = 22000
max_adc_value = 65535

colour_list = [
    255, 0xFF00, 0xFFFF, 0xFF0000,
    0xFF00FF, 0xFFFF00, 0xFFFFFF,
    0x30FF00, 0x60FF00
    ]

class RTC_PCF8563:
    def __init__(self):
        self.i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=100000)
        self.days_text = ["Sun", "Mon", "Tue", "Wed", "Thurs", "Fri", "Sat"]
        
        #print(self.i2c.scan())
    def from_bcd(self, value):
        return (value >> 4) * 10 + (value & 0x0F)
    
    def to_bcd(self, value):
        return ((value // 10) << 4) + (value % 10)
    
    def to_bcd_byte(self, value: int):
        value = self.to_bcd(value)
        return value.to_bytes(1, "big")
    
    def write_byte_to_bcd_register(self, register, value):
        self.i2c.writeto_mem(81, register, self.to_bcd_byte(value))
        
    #def get_bcd_register(register, mask):
    #    value = self.i2c.readfrom_mem(81, 2, 1)[0]
    #    value &= mask
    #    return self.from_bcd(value)
        
    def get_time(self):
        seconds = self.i2c.readfrom_mem(81, 2, 1)[0]
        valid = seconds < 128
        seconds = self.from_bcd(seconds & 0x7F)
        minutes = self.from_bcd(self.i2c.readfrom_mem(81, 3, 1)[0] & 0x7F)
        hours = self.from_bcd(self.i2c.readfrom_mem(81, 4, 1)[0] & 0x3F)
        days = self.from_bcd(self.i2c.readfrom_mem(81, 5, 1)[0] & 0x3F)
        weekdays = self.i2c.readfrom_mem(81, 6, 1)[0] & 0x07
        century_months = self.i2c.readfrom_mem(81, 7, 1)[0]
        century = century_months >> 7
        month = self.from_bcd(century_months & 0x1F)
        years = self.from_bcd(self.i2c.readfrom_mem(81, 8, 1)[0])
        years += (100*(century+19))

        #print("%d/%d/%d %d:%d:%d (%s) %d" % (years, month, days, hours, minutes, seconds, repr(valid), weekdays))
        return (years, month, days, hours, minutes, seconds, valid, weekdays)

    def print_time(self):
        (years, month, days, hours, minutes, seconds, valid, weekdays) = self.get_time()
        if valid:
            weekdays = self.days_text[weekdays]
        print("%d/%d/%d %d:%d:%d (%s) %s" % (years, month, days, hours, minutes, seconds, repr(valid), weekdays))
        
    def set_time(self, years, month, days, hours, minutes, seconds, weekdays):
        self.write_byte_to_bcd_register(2, seconds)
        self.write_byte_to_bcd_register(3, minutes)
        self.write_byte_to_bcd_register(4, hours)
        self.write_byte_to_bcd_register(5, days)
        self.write_byte_to_bcd_register(6, weekdays)
        cm = month
        # Always after 200, so set top bit
        cm += 80
        # make years two digits
        years %= 100
        self.write_byte_to_bcd_register(7, cm)
        self.write_byte_to_bcd_register(8, years)
    
    def set_if_not_valid(self):
        (years, month, days, hours, minutes, seconds, valid, days) = self.get_time()
        if not valid:
            now = time.time()
            (year, month, day, hour, minute, second, weekday, yearday) = time.localtime(now)

            print("Setting time - %d:%d:%d" % (hour, minute, second))

            # Python uses 0=Mon, PCF8563 uses 0=Sun
            weekday += 1
            if weekday >= 8:
                weekday = 0
            self.set_time(year, month, day, hour, minute, second, weekday)
        
class TemperatureLogger:
    def __init__(self):
        self.led = Pin(25, Pin.OUT)
        self.S0 = Pin(8, Pin.OUT)
        self.S1 = Pin(9, Pin.OUT)
        self.S2 = Pin(27, Pin.OUT)
        self.adc = ADC(26) # Connect to GP26, which is channel 0
        
        self.nominal_ntc_resistances = [20, 20, 20, 20, 20, 20, 20, 10]
        
        spi=SPI(1,baudrate=40000000,sck=Pin(10),mosi=Pin(11),miso=Pin(12))
        sd=sdcard.SDCard(spi,Pin(13))
        vfs=os.VfsFat(sd)
        os.mount(sd,'/sd')
        print("FILES:", os.listdir('/sd'))
    
    def write_line(self, line):
        file = open("/sd/temp_log.txt","a")
        file.write(line+"\n")
        file.close()
        
    def mux(self, channel):
        if channel >= 0 and channel <= 7:
            S0_value = channel & 1
            S1_value = (channel >> 1) & 1
            S2_value = (channel >> 2) & 1
            self.S0.value(S0_value)
            self.S1.value(S1_value)
            self.S2.value(S2_value)

    def select_terminal(self, terminal):
        ''' NOTE: This is terminal inputs, not MUX channels ''' 
        if terminal >= 1 and terminal <= 8:
            if terminal == 8:
                terminal = 0            
            self.mux(terminal)

    def read_terminal_value(self, terminal):
        self.select_terminal(terminal)
        time.sleep(0.1)
        reading = self.adc.read_u16()
        return reading

    def read_terminal_voltage(self, terminal):
        reading = self.read_terminal_value(terminal) * adc_conversion_factor
        print(terminal, "=", reading, "v")
        return reading
    
    def read_all_terminal_volts(self):
        for i in range(8):
            self.read_terminal_voltage(i+1)
    
    def read_terminal_resistance(self, terminal):
        reading = self.read_terminal_value(terminal)
        ratio = reading/max_adc_value
        if ratio < 1:
            resistance = ratio * terminal_pull_up_resistor / ( 1 - ratio)
            if resistance > 6000000:
                resistance = "Open Circuit"
        else:
            resistance = "Open Circuit"
            
        print(terminal, "=", resistance, "ohms")
        return resistance

    def read_all_terminal_resistances(self):
        for i in range(8):
            self.read_terminal_resistance(i+1)
    
    def log_raw(self, rtc):
        (years, month, days, hours, minutes, seconds, valid, weekdays) = rtc.get_time()
        date_and_time = "{},{},{},{},{},{},{},{}".format(years, month, days, hours, minutes, seconds, valid, rtc.days_text[weekdays])

        v = []
        for i in range(8):
            v.append(self.read_terminal_value(i+1))
        
        data = "{},{},{},{},{},{},{},{},{}".format(date_and_time, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7])
        print(data)
        self.write_line(data)
        
    def main(self, loop=False):
        rtc = RTC_PCF8563()
        rtc.set_if_not_valid()

        colour = 0

        while True:
            np[0] = colour_list[colour]
            sm.put(np,8)
            colour += 1
            if colour >= len(colour_list):
                colour = 0

            rtc.print_time()
            self.led.value(1)
            self.log_raw(rtc)
            self.read_all_terminal_resistances()
            self.led.value(0)
            np[0] = 0
            sm.put(np,8)

            if loop == False:
                break
            
            time.sleep(30)
            
        #timer_one = machine.Timer()
        # Timer one initialization for on board blinking LED at 200mS interval
        #timer_one.init(freq=5, mode=machine.Timer.PERIODIC, callback=BlinkLED)

    def show_file(self):
        file = open("/sd/temp_log.txt","r")
        
        while True:
            # Get next line from file
            line = file.readline()
            
            # if line is empty, end of file is reached
            if not line:
                break
            
            print(line.strip())
        
        file.close()        

if __name__ == "__main__":
    logger = TemperatureLogger()
    log = True
    if log:
        logger.main()
    else:
        logger.show_file()
    
    erase_file = False
    if erase_file:
        file = open("/sd/temp_log.txt","w")
        file.close()
    
