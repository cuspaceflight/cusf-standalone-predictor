import os
import random
import csv
import statsd

from .dummy import dummy_prank
from .gravity import prank_path as gravity_prank
from .writing import prank_path as writing_prank

# statsd should have been initted

def prank_hook(uuid, preds_dir):
    flight_path = os.path.join(preds_dir, uuid, "flight_path.csv")
    pranked_path = os.path.join(preds_dir, uuid, "flight_path_prank.csv")

    # make it deterministic
    our_random = random.Random(uuid)

    prank = choose_prank(our_random)

    with open(flight_path) as real_csv:
        with open(pranked_path, 'w') as pranked_csv:
            reader = csv.reader(real_csv, dialect='excel')
            writer = csv.writer(pranked_csv, dialect='excel')

            # optionally iterables. Applying types twice sanity checks output
            # to a certain extent
            writer.writerows(types(prank(types(reader), our_random, uuid)))

def types(reader):
    for (time, lat, lon, alt) in reader:
        yield (int(time), float(lat), float(lon), float(alt))

def choose_prank(random):
    if random.randrange(2) == 0:
        statsd.increment('prank.gravity.picked')
        print "GRAVITY"
        return gravity_prank
    else:
        statsd.increment('prank.writing.picked')
        print "WRITING"
        return writing_prank
