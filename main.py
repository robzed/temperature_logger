import machine, time

def doBeep(freq, duration):
    global buzzer
    buzzer.freq(freq)             # set frequency (notes)
    buzzer.duty_u16(19660)        # 30% duty cycle
    time.sleep(duration)

def doSilence(duration):
    global buzzer
    buzzer.duty_u16(0)            # 0% duty cycle
    time.sleep(duration)

def doStartBeep():
    global buzzer
    buzzer = machine.PWM(machine.Pin(18))  # set pin 18 as PWM OUTPUT
    doSilence(0)
    doBeep(2093, 0.1)
    doSilence(0.1)
    doBeep(294, 0.1)
    doSilence(0)
    doBeep(330, 0.1)
    doSilence(0.1)


from temperature import TemperatureLogger

doStartBeep()

logger = TemperatureLogger()
logger.main(loop=True)
