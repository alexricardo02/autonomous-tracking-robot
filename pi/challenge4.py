from irobot_edu_sdk.backend.bluetooth import Bluetooth
from irobot_edu_sdk.robots import event, hand_over, Color, Robot, Root, Create3
from irobot_edu_sdk.music import Note

robot = Create3(Bluetooth("MyRobot_Lukas"))

stop = False

# Event listener triggered when either the left or right bump sensor detects a collision
@event(robot.when_bumped, [True, True])
async def bumped(robot):
    global stop 
    await robot.set_lights_on_rgb(255, 0, 0)
    stop = True 
    await robot.stop()


# Main kinematic task executed when the program starts
@event(robot.when_play)
async def play(robot):
    for _ in range(4):
        print(stop)
        if stop:
            break  # Terminate the loop immediately if a collision was detected
            
        await robot.move(40)
        
        print(stop)
        if stop:
            break 
            
        await robot.turn_left(90)  # Rotate 90 degrees to the left


# Parallel task executed concurrently to handle the visual state indicator
@event(robot.when_play)
async def luces(robot):
    while True:
        if stop:
            break
            
        await robot.set_lights_on_rgb(0, 255, 0)   # Green
        await robot.wait(0.3)
        await robot.set_lights_on_rgb(0, 0, 255)  # Blue
        await robot.wait(0.3)

robot.play()