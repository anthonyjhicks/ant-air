def estimate_duration_minutes(distance_miles):
    if not distance_miles:
        return None

    if distance_miles <= 250:
        cruise_speed_mph = 300
    elif distance_miles <= 1000:
        cruise_speed_mph = 420
    elif distance_miles <= 2000:
        cruise_speed_mph = 480
    else:
        cruise_speed_mph = 520

    taxi_buffer_minutes = 45
    flight_minutes = (distance_miles / cruise_speed_mph) * 60
    return int(round(flight_minutes + taxi_buffer_minutes))
