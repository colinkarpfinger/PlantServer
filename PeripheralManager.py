import time
from datetime import datetime
import sqlite3 
import gpiozero 
import psutil
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn



dbname='db/sensorData.db'

relays = {                              # set up relays
        '5': gpiozero.OutputDevice(5, active_high=False, initial_value=False),
        '6': gpiozero.OutputDevice(6, active_high=False, initial_value=False),
        '13': gpiozero.OutputDevice(13, active_high=False, initial_value=False),
        '19': gpiozero.OutputDevice(19, active_high=False, initial_value=False),
        '26': gpiozero.OutputDevice(26, active_high=False, initial_value=False),
        '16': gpiozero.OutputDevice(16, active_high=False, initial_value=False),
        '20': gpiozero.OutputDevice(20, active_high=False, initial_value=False),
        '21': gpiozero.OutputDevice(21, active_high=False, initial_value=False)
        }

i2c = busio.I2C(board.SCL, board.SDA)   # set up ADC 
ads = ADS.ADS1115(i2c)
channels = []
channels.append(AnalogIn(ads, ADS.P0))
channels.append(AnalogIn(ads, ADS.P1))
channels.append(AnalogIn(ads, ADS.P2))
channels.append(AnalogIn(ads, ADS.P3))

def logPiData(_cpuTemp, _ram_percent_used):
    conn=sqlite3.connect(dbname)
    curs=conn.cursor()
    curs.execute("INSERT INTO pi_data values(datetime('now'),(?),(?))", (_cpuTemp, _ram_percent_used))
    conn.commit()
    conn.close()

def logAdcData(_channel,_adc_count,_voltage):
    conn=sqlite3.connect(dbname)
    curs=conn.cursor()
    curs.execute("INSERT INTO adc_data values(datetime('now'),(?),(?),(?))", (_channel, _adc_count,_voltage))
    conn.commit()
    conn.close()

def GetGpioNumbers():
    conn=sqlite3.connect(dbname)
    curs=conn.cursor()
    gpioNums = []
    for row in curs.execute("SELECT gpio_number FROM plant_config"):
        gpioNums.append(row[0]) 
    return gpioNums

def GetCurrentStatus(gpio):
    conn=sqlite3.connect(dbname)
    curs=conn.cursor()
    curs.execute("SELECT status,duration_seconds FROM pump_status WHERE gpio_number = (?) ORDER BY timestamp DESC LIMIT 1", (gpio,))
    row = curs.fetchone() 
    if row == None:
        return "",0
    else:
        status,duration = row 
        return status,duration

def SetCurrentStatus(gpio, status, duration_seconds):
    conn=sqlite3.connect(dbname)
    curs=conn.cursor()
    curs.execute("INSERT INTO pump_status values(datetime('now'),(?),(?),(?))", (gpio, status, duration_seconds))
    conn.commit()

def main():
    print(str(datetime.now())+' peripheralManager.py: Starting up...')
    logDataIntervalSeconds = 60     # log data every 60 seconds
    pumpCheckIntervalSeconds = 1    # check the pump queue every _ (testing w 1 second)
    pumpCheckTickCount = 0
    pumpRunDurationSeconds = 0
    pumpRunTickCount = 0 
    logDataTickCount = 0	
    pumpRunning = False
    currentPumpNumber = 0 
    while True:
        if not pumpRunning and pumpCheckTickCount >= pumpCheckIntervalSeconds: # wait til pump is off to check for next item in queue. 
            for gpio in GetGpioNumbers(): 
                status, durationSeconds = GetCurrentStatus(str(gpio))   # get latest row in pump status table
                if status == 'requestrun':                              # if == requestrun, update status to running, run pump for specified time 
                    SetCurrentStatus(gpio, 'running', durationSeconds)  
                    print(str(datetime.now())+' peripheralManager.py: Turning ON gpio: '+str(gpio)+' for '+str(durationSeconds)+ ' seconds' )
                    if str(gpio) in relays:
                        relays[str(gpio)].on()
                    else:
                        print(str(datetime.now())+' peripheralManager.py: error: unknown gpio number')
                    pumpRunning = True 
                    currentPumpNumber = gpio
                    pumpRunDurationSeconds = durationSeconds
                    #pumpRunDurationSeconds = 2
                    pumpRunTickCount = 0 
                    break


        if pumpRunning and pumpRunTickCount >= pumpRunDurationSeconds:
            print(str(datetime.now())+' peripheralManager.py: Turning OFF gpio: '+str(gpio)+' for '+str(durationSeconds)+ ' seconds' )
            if str(currentPumpNumber) in relays:
                relays[str(currentPumpNumber)].off()
            else:
                print(str(datetime.now())+' peripheralManager.py: error: unknown gpio number')
            pumpRunning = False
            pumpRunTickCount = 0 
            SetCurrentStatus(gpio, 'ready', 0)

        if logDataTickCount >= logDataIntervalSeconds:
        
            cpu = gpiozero.CPUTemperature()                 # get rpi temp / ram data 
            ram = psutil.virtual_memory()
            ram_percent_used = (ram.total - ram.available) / ram.total
            logPiData(cpu.temperature,ram_percent_used)     # log to db 

            i=0
            for chan in channels:                           # get ADC data
                try:
                    logAdcData(i, chan.value, chan.voltage)     # log to db 
                except: 
                    print(str(datetime.now())+' peripheralManager.py: error: couldn\'t read adc')

                i+=1
            
            logDataTickCount = 0 
            
        time.sleep(1)
        logDataTickCount += 1
        pumpCheckTickCount += 1 
        if pumpRunning:
            pumpRunTickCount += 1
        

    #end while 
#end main



if __name__ == '__main__':
    main()
