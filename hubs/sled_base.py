from pybricks.parameters import Port, Stop
from pybricks.pupdevices import Motor
from pybricks.tools import wait


def pybricks_import(name, fromlist=None):
    try:
        if fromlist is None:
            return __import__(name)
        return __import__(name, None, None, fromlist)
    except TypeError:
        if fromlist is None:
            return __import__(name, None, None, [])
        return __import__(name, None, None, list(fromlist))


def try_import_hub():
    candidates = [
        ("pybricks.hubs", "PrimeHub"),
        ("pybricks.hubs", "TechnicHub"),
        ("pybricks.hubs", "ThisHub"),
        ("pybricks", "PrimeHub"),
        ("pybricks", "TechnicHub"),
        ("pybricks", "ThisHub"),
    ]
    for module_name, class_name in candidates:
        try:
            module = pybricks_import(module_name, fromlist=[class_name])
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except Exception:
            pass
    return None


HubClass = try_import_hub()
if HubClass is None:
    raise ImportError("No compatible hub class found for sled_base.py")


# ===== Sled base calibration config =====
WEIGHT_BOX_PORT = Port.B

# Keep this low to protect mechanics during endstop search.
CALIB_SPEED_DPS = 60
CALIB_FINE_SPEED_DPS = 30
CALIB_DUTY_LIMIT = 35
CALIB_DUTY_STEP = 10
CALIB_MAX_RETRIES = 3
CALIB_MIN_TRAVEL_DEG = 4000
CALIB_BACKOFF_DEG = 80

# Back off from hard stop after homing.
HOME_OFFSET_DEG = 20


def run_until_stalled_safe(motor, speed, duty_limit):
    try:
        motor.run_until_stalled(speed, then=Stop.HOLD, duty_limit=duty_limit)
    except TypeError:
        motor.run_until_stalled(speed, then=Stop.HOLD)


def seek_endstop(weight_motor, direction, duty_limit):
    coarse_speed = CALIB_SPEED_DPS if direction > 0 else -CALIB_SPEED_DPS
    fine_speed = CALIB_FINE_SPEED_DPS if direction > 0 else -CALIB_FINE_SPEED_DPS

    # Coarse seek towards endstop.
    run_until_stalled_safe(weight_motor, coarse_speed, duty_limit)
    coarse = weight_motor.angle()

    # Back off, then re-approach slowly for repeatable final contact.
    backoff_target = coarse - direction * CALIB_BACKOFF_DEG
    weight_motor.run_target(120, backoff_target, then=Stop.HOLD, wait=True)
    wait(150)

    run_until_stalled_safe(weight_motor, fine_speed, duty_limit)
    fine = weight_motor.angle()
    return fine


def calibrate_weight_box(weight_motor):
    end_1 = 0
    end_2 = 0
    duty_limit = CALIB_DUTY_LIMIT

    for attempt in range(CALIB_MAX_RETRIES):
        end_1 = seek_endstop(weight_motor, 1, duty_limit)
        print("CAL end_1:", end_1, "attempt", attempt + 1, "duty", duty_limit)
        wait(300)

        end_2 = seek_endstop(weight_motor, -1, duty_limit)
        print("CAL end_2:", end_2, "attempt", attempt + 1, "duty", duty_limit)
        wait(300)

        travel = abs(end_1 - end_2)
        if travel >= CALIB_MIN_TRAVEL_DEG:
            break

        # False stall likely happened in a sticky mid-zone. Push through a bit
        # in both directions before retrying with more duty.
        try:
            weight_motor.run_angle(220, 240, then=Stop.HOLD, wait=True)
            wait(150)
            weight_motor.run_angle(220, -240, then=Stop.HOLD, wait=True)
        except Exception:
            pass

        duty_limit += CALIB_DUTY_STEP
        print("CAL retry: travel too small", travel, "next duty", duty_limit)

    travel = abs(end_1 - end_2)
    if travel < CALIB_MIN_TRAVEL_DEG:
        raise RuntimeError(
            "Calibration failed: false stall before endstop (travel=%d < %d). Reduce friction or increase duty." %
            (travel, CALIB_MIN_TRAVEL_DEG)
        )

    # Determine back/front from measured limits so calibration is robust
    # even if motor direction is swapped.
    back = min(end_1, end_2)
    front = max(end_1, end_2)

    home = back + HOME_OFFSET_DEG
    weight_motor.run_target(180, home, then=Stop.HOLD, wait=True)

    travel = abs(end_1 - end_2)
    print("CAL back:", back)
    print("CAL front:", front)
    print("CAL home:", home)
    print("CAL travel_deg:", travel)

    return {
        "end_1": end_1,
        "end_2": end_2,
        "back": back,
        "front": front,
        "home": home,
        "travel_deg": travel,
    }


def main():
    hub = HubClass()
    try:
        hub.system.set_stop_button(None)
    except Exception:
        pass

    weight_motor = Motor(WEIGHT_BOX_PORT)
    print("SLED BASE: calibration start")
    result = calibrate_weight_box(weight_motor)
    print("SLED BASE: calibration done", result)

    # Hold position so you can inspect mechanics.
    while True:
        wait(100)


main()
