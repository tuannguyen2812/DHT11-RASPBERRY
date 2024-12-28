import utime as time
from machine import Pin, I2C
from micropython import const
import array

# Define exceptions
class InvalidChecksum(Exception):
    pass

class InvalidPulseCount(Exception):
    pass

# Constants for DHT11
MAX_UNCHANGED = const(100)
MIN_INTERVAL_US = const(200000)
HIGH_LEVEL = const(50)
EXPECTED_PULSES = const(84)

# LCD constants
LCD_I2C_ADDR = 0x27
LCD_ROWS = 2
LCD_COLS = 16
LCD_CMD = 0
LCD_DATA = 1
LCD_CLEAR = 0x01
LCD_HOME = 0x02
LCD_ENTRY_MODE_SET = 0x04
LCD_DISPLAY_CONTROL = 0x08
LCD_CURSOR_SHIFT = 0x10
LCD_FUNCTION_SET = 0x20
LCD_BACKLIGHT = 0x08

# DHT11 class
class DHT11:
    _temperature: float
    _humidity: float

    def __init__(self, pin):
        self._pin = pin
        self._last_measure = time.ticks_us()
        self._temperature = -1
        self._humidity = -1

    def measure(self):
        current_ticks = time.ticks_us()
        if time.ticks_diff(current_ticks, self._last_measure) < MIN_INTERVAL_US and (
            self._temperature > -1 or self._humidity > -1
        ):
            return

        self._send_init_signal()
        pulses = self._capture_pulses()
        buffer = self._convert_pulses_to_buffer(pulses)
        self._verify_checksum(buffer)

        self._humidity = buffer[0] + buffer[1] / 10
        self._temperature = buffer[2] + buffer[3] / 10
        self._last_measure = time.ticks_us()

    @property
    def humidity(self):
        self.measure()
        return self._humidity

    @property
    def temperature(self):
        self.measure()
        return self._temperature

    def _send_init_signal(self):
        self._pin.init(Pin.OUT, Pin.PULL_DOWN)
        self._pin.value(1)
        time.sleep_ms(50)
        self._pin.value(0)
        time.sleep_ms(18)

    def _capture_pulses(self):
        pin = self._pin
        pin.init(Pin.IN, Pin.PULL_UP)

        val = 1
        idx = 0
        transitions = bytearray(EXPECTED_PULSES)
        unchanged = 0
        timestamp = time.ticks_us()

        while unchanged < MAX_UNCHANGED:
            if val != pin.value():
                if idx >= EXPECTED_PULSES:
                    raise InvalidPulseCount()
                now = time.ticks_us()
                transitions[idx] = now - timestamp
                timestamp = now
                idx += 1
                val = 1 - val
                unchanged = 0
            else:
                unchanged += 1
        pin.init(Pin.OUT, Pin.PULL_DOWN)
        if idx != EXPECTED_PULSES:
            raise InvalidPulseCount()
        return transitions[4:]

    def _convert_pulses_to_buffer(self, pulses):
        binary = 0
        for idx in range(0, len(pulses), 2):
            binary = binary << 1 | int(pulses[idx] > HIGH_LEVEL)

        buffer = array.array("B")
        for shift in range(4, -1, -1):
            buffer.append(binary >> shift * 8 & 0xFF)
        return buffer

    def _verify_checksum(self, buffer):
        checksum = 0
        for buf in buffer[0:4]:
            checksum += buf
        if checksum & 0xFF != buffer[4]:
            raise InvalidChecksum()

# LCD class
class LCD1602:
    def __init__(self, i2c, addr=LCD_I2C_ADDR):
        self.i2c = i2c
        self.addr = addr
        self.backlight = LCD_BACKLIGHT
        self._init_lcd()

    def _write(self, data, mode):
        high = (data & 0xF0) | self.backlight | mode
        low = ((data << 4) & 0xF0) | self.backlight | mode
        self.i2c.writeto(self.addr, bytearray([high | 0x04, high, low | 0x04, low]))

    def _init_lcd(self):
        try:
            self._write(LCD_FUNCTION_SET | 0x08, LCD_CMD)  # 2 lines, 5x8 dots
            self._write(LCD_DISPLAY_CONTROL | 0x04, LCD_CMD)  # Display on, cursor off
            self.clear()
        except OSError:
            print("LCD initialization failed. Retrying...")
            time.sleep(2)  
            self._init_lcd()

    def clear(self):
        self._write(LCD_CLEAR, LCD_CMD)
        time.sleep_ms(2)

    def write(self, row, col, text):
        addr = 0x80 + (0x40 * row) + col
        self._write(addr, LCD_CMD)
        for char in text:
            self._write(ord(char), LCD_DATA)

# Main code
if __name__ == "__main__":
    dht_pin = Pin(28, Pin.OUT, Pin.PULL_DOWN)
    dht_sensor = DHT11(dht_pin)
    i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=500000)
    lcd = LCD1602(i2c)
    
    degree_char = chr(0xDF)
    
    while True:
        try:
            temp = dht_sensor.temperature
            hum = dht_sensor.humidity
            print("Temperature: {}°C".format(temp))
            print("Humidity: {}%".format(hum))
            
            lcd.clear()
            lcd.write(0, 0, "Temp: {:.1f}{}C".format(temp, degree_char))
            lcd.write(1, 0, "Humi: {}%".format(hum))
        except InvalidChecksum:
            lcd.clear()
            lcd.write(0, 0, "Checksum error!")
        time.sleep(2)

