from itertools import izip, count

def dummy_prank(flight_path, random, uuid):
    assert random.random() < 0.9
    for ((time, lat, lon, alt), i) in izip(flight_path, count()):
        if i % 20 >= 10:
            lat += 1
        yield (time, lat, lon, alt)

