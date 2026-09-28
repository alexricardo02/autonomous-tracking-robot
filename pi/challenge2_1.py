import asyncio
from irobot_edu_sdk.backend.bluetooth import Bluetooth
from irobot_edu_sdk.robots import event, hand_over, Create3
from pynput import keyboard

# Configuration
robot = Create3(Bluetooth('ROBO-NAME'))
speed = 15 # Speed in cm/s
keys_pressed = set()

def on_press(key):
    try:
        if hasattr(key, 'char'): keys_pressed.add(key.char)
    except AttributeError: pass

def on_release(key):
    try:
        if hasattr(key, 'char') and key.char in keys_pressed:
            keys_pressed.remove(key.char)
    except AttributeError: pass
    if key == keyboard.Key.esc: return False

@event(robot.when_play)
async def play(robot):
    
    while True:
        # motor control logic based on keys pressed
        if 'w' in keys_pressed:
            await robot.set_wheel_speeds(speed, speed)
        elif 's' in keys_pressed:
            await robot.set_wheel_speeds(-speed, -speed)
        elif 'a' in keys_pressed:
            await robot.set_wheel_speeds(-speed, speed)
        elif 'd' in keys_pressed:
            await robot.set_wheel_speeds(speed, -speed)
        else:
            await robot.set_wheel_speeds(0, 0)
        
        await asyncio.sleep(0.05) 

listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()

robot.play()