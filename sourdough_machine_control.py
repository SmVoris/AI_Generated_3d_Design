from machine import Pin, PWM, I2C, ADC
import utime
import network
import urequests
from ssd1306 import SSD1306_I2C
import onewire, ds18x20
import hx711

# Wi-Fi configuration
SSID = "your_wifi_ssid"
PASSWORD = "your_wifi_password"
WEBHOOK_URL = "your_webhook_url"  # E.g., IFTTT or Discord webhook

# Pin assignments
discard_servo = PWM(Pin(0))
flour_servo = PWM(Pin(1))
water_pump = Pin(2, Pin.OUT)
stir_motor = Pin(3, Pin.OUT)
heating_pad = Pin(4, Pin.OUT)
button_manual = Pin(5, Pin.IN, Pin.PULL_UP)
button_adjust = Pin(6, Pin.IN, Pin.PULL_UP)
buzzer = Pin(7, Pin.OUT)
float_sensor = Pin(8, Pin.IN, Pin.PULL_UP)
temp_sensor_pin = Pin(22)
hx711_sck = Pin(10)
hx711_dt = Pin(11)
oled_scl = Pin(9)
oled_sda = Pin(8)

# Initialize components
discard_servo.freq(50)
flour_servo.freq(50)
i2c = I2C(0, scl=oled_scl, sda=oled_sda)
oled = SSD1306_I2C(128, 64, i2c)
ds_sensor = ds18x20.DS18X20(onewire.OneWire(temp_sensor_pin))
roms = ds_sensor.scan()
load_cell = hx711.HX711(hx711_sck, hx711_dt)

# Feeding parameters
FEED_INTERVAL = 12 * 60 * 60  # 12 hours in seconds
DISCARD_WEIGHT = 100  # Grams to discard
FLOUR_WEIGHT = 50     # Grams of flour
WATER_VOLUME = 50     # mL of water
STIR_TIME = 10        # Seconds to stir
TEMP_MIN = 20         # °C
TEMP_MAX = 25         # °C
CALIBRATION_FACTOR = 1000  # Adjust based on load cell calibration

# Wi-Fi connection
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    for _ in range(10):
        if wlan.isconnected():
            oled.text("WiFi Connected", 0, 0)
            oled.show()
            return True
        utime.sleep(1)
    oled.text("WiFi Failed", 0, 0)
    oled.show()
    return False

# Send notification
def send_notification(message):
    try:
        urequests.post(WEBHOOK_URL, json={"value1": message})
    except:
        pass

# Calibrate load cell
def calibrate_load_cell():
    load_cell.tare()
    oled.fill(0)
    oled.text("Place 100g weight", 0, 0)
    oled.show()
    utime.sleep(5)
    reading = load_cell.read_average(10)
    global CALIBRATION_FACTOR
    CALIBRATION_FACTOR = reading / 100  # Grams per unit
    oled.fill(0)
    oled.text("Calibrated", 0, 0)
    oled.show()

# Read weight
def read_weight():
    return load_cell.read_average(10) / CALIBRATION_FACTOR

# Read temperature
def read_temperature():
    ds_sensor.convert_temp()
    utime.sleep_ms(750)
    for rom in roms:
        return ds_sensor.read_temp(rom)
    return 0

# Control heating pad
def control_temperature():
    temp = read_temperature()
    if temp < TEMP_MIN:
        heating_pad.value(1)
    elif temp > TEMP_MAX:
        heating_pad.value(0)
    return temp

# Feed starter
def feed_starter():
    oled.fill(0)
    oled.text("Feeding...", 0, 0)
    oled.show()
    
    # Check supplies
    if float_sensor.value() == 0:
        oled.text("Low Water!", 0, 10)
        oled.show()
        buzzer.value(1)
        utime.sleep(1)
        buzzer.value(0)
        send_notification("Low water in reservoir")
        return
    
    # Discard starter
    initial_weight = read_weight()
    discard_servo.duty_u16(6500)  # Open trapdoor
    while read_weight() > initial_weight - DISCARD_WEIGHT:
        utime.sleep(0.1)
    discard_servo.duty_u16(5000)  # Close trapdoor
    
    # Dispense flour
    flour_servo.duty_u16(6000)  # Run auger
    initial_weight = read_weight()
    while read_weight() < initial_weight + FLOUR_WEIGHT:
        utime.sleep(0.1)
    flour_servo.duty_u16(0)  # Stop auger
    
    # Dispense water
    water_pump.value(1)
    utime.sleep(WATER_VOLUME / 10)  # Calibrated for 10mL/s
    water_pump.value(0)
    
    # Stir
    stir_motor.value(1)
    utime.sleep(STIR_TIME)
    stir_motor.value(0)
    
    # Update status
    global last_feed, next_feed
    last_feed = utime.time()
    next_feed = last_feed + FEED_INTERVAL
    temp = read_temperature()
    weight = read_weight()
    oled.fill(0)
    oled.text(f"Temp: {temp:.1f}C", 0, 0)
    oled.text(f"Weight: {weight:.1f}g", 0, 10)
    oled.text(f"Next: {utime.localtime(next_feed)[3:5]}", 0, 20)
    oled.show()
    send_notification(f"Fed starter: {weight:.1f}g, {temp:.1f}C")

# Initialize
connect_wifi()
calibrate_load_cell()
last_feed = utime.time()
next_feed = last_feed + FEED_INTERVAL

# Main loop
while True:
    current_time = utime.time()
    
    # Control temperature
    temp = control_temperature()
    
    # Check for scheduled feeding
    if current_time >= next_feed:
        feed_starter()
    
    # Check for manual feed
    if button_manual.value() == 0:
        feed_starter()
        utime.sleep(0.5)
    
    # Check for schedule adjustment
    if button_adjust.value() == 0:
        FEED_INTERVAL = 24 * 60 * 60 if FEED_INTERVAL == 12 * 60 * 60 else 12 * 60 * 60
        next_feed = last_feed + FEED_INTERVAL
        oled.fill(0)
        oled.text(f"Interval: {FEED_INTERVAL//3600}h", 0, 0)
        oled.show()
        utime.sleep(0.5)
    
    utime.sleep(0.1)