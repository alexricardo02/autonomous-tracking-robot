from irobot_edu_sdk.backend.bluetooth import Bluetooth
from irobot_edu_sdk.robots import event, hand_over, Color, Robot, Root, Create3
from irobot_edu_sdk.music import Note

robot = Create3(Bluetooth())

# This is a global variable. So it will need to be referenced as "global stop" from inside functions.
stop = False

@event(robot.when_bumped, [True, True])
async def bumped(robot):
    global stop  # Please note the "global" keyword here!
    await robot.set_lights_on_rgb(255, 0, 0)
    stop = True  # This is what will tell the other loops (running in parallel in other tasks) to stop.
    await robot.stop()  # This method will stop all the robot's actuators.

@event(robot.when_play)
async def play(robot):
    for _ in range(4):
        print(stop)
        if stop:
            break  # This will stop the for loop!
        await robot.move(40)
        print(stop)
        if stop:
            break  # This will stop the for loop! Need to check before every command, since we don't know when we will be asked to stop.
        await robot.turn_left(90)

@event(robot.when_play)
async def play(robot):
    while True:
        if stop:
            break  # This will stop the while loop!
        await robot.set_lights_on_rgb(0, 255, 0)
        await robot.wait(0.3)
        await robot.set_lights_on_rgb(0, 0, 255)
        await robot.wait(0.3)

robot.play()