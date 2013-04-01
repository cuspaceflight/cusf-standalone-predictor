import utm
import pyproj
import psycopg2
import numpy as np

targets = [
    # UTM zone, latitude, longitude, identifier
    (30, 51.4715, -0.4520, "LHR"),
    (31, 49.009722, 2.547778, "CDG"),
    (32, 50.033333, 8.570556, "FRA"),
    (34, 52.165833, 20.967222, "WAW"),
    (54, -34.945, 138.530556, "ADL"),
    (50, -31.940278, 115.966944, "PER"),
    (56, -33.946111, 151.177222, "SYD"),
    (29, 53.421389, -6.27, "DUB"),
    (16, 41.978611, -87.904722, "ORD"),
    (11, 33.9425, -118.408056, "LAX"),
    (13, 39.861667, -104.673056, "DEN"),
    (18, 40.639722, -73.778889, "JFK")
]

THRESHOLD_DISTANCE = 500.0 #m
DT = 5.0 #s

geod = pyproj.Geod(ellps='WGS84')

def find_closest_target(path):
    """Return the path up to the closest point to a target, and that target."""
    burstidx = np.argmax([p[3] for p in path])
    src_lat, src_lng = path[burstidx][1], path[burstidx][2]
    if src_lng > 180.0:
        src_lng -= 360.0
    conn = psycopg2.connect("dbname=airports")
    cur = conn.cursor()
    cur.execute("SELECT latitude, longitude,"
                "       ST_Distance(geom, "
                "                   ST_GeomFromText('POINT(%s %s)', 4326)) "
                "       AS distance "
                "FROM airports ORDER BY distance LIMIT 1", (src_lng, src_lat))
    lat, lng = cur.fetchone()[:2]
    #target_distances = []
    #for point in path:
        #for target in targets:
            #dist = geod.inv(point[2], point[1], target[2], target[1])[2]
            #target_distances.append((dist, target))
    #dist, target = min(target_distances[len(path)/4:])
    #idx = target_distances.index((dist, target))
    #return path[:idx+1], target
    return path[:burstidx + 1], (utm.from_latlon(lat, lng)[2], lat, lng)

#G = 6.674E-11
def acceleration(r1, r2):
    """Compute the acceleration due to a mass m at position r2 on object r1"""
    r = r1 - r2
    dist = np.linalg.norm(r)
    r /= dist
    return -0.5 * r
    #return -r * ((G * ATTRACTOR_MASS) / np.power(dist, 2))

def compute_initial_state(path, target, proj):
    """Return the initial state vector and target position."""
    r_target = np.array(proj(target[2], target[1]))
    r = np.array(proj(path[-1][2], path[-1][1]))
    r_old = np.array(proj(path[-2][2], path[-2][1]))
    v = (r - r_old) / (path[-1][0] - path[-2][0])
    #v /= np.linalg.norm(v)
    #v = r - r_target
    #v[0], v[1] = -v[1], v[0]
    #v /= np.linalg.norm(v)
    #v *= np.sqrt((G * ATTRACTOR_MASS) / np.linalg.norm(r - r_target))
    #v = np.array((0.0, 0.0))
    a = acceleration(r, r_target)
    return r, v, a, r_target

def extend_path(path, r, proj):
    """Stick r onto the end of path."""
    lng, lat = proj(r[0], r[1], inverse=True)
    path.append((path[-1][0] + DT, lat, lng, 42.0))

def velocity_verlet(r, v, a, r_target):
    """Numerically integrate gravity towards target"""
    rnew = r + v * DT + 0.5 * a * (DT**2)
    anew = acceleration(rnew, r_target)
    vnew = v + 0.5 * DT * (a + anew)
    return rnew, vnew, anew

def velocity_loss(r, v, a, r1, r_target):
    #v *= 1.0 - 1.0/(0.05*v + 1)
    d = np.linalg.norm(r - r_target)
    v *= 1.0 - (1/((d/2000.0)+50.0))
    #return v * 0.98
    return v

def prank_path(path, random, uuid, debug=False):
    """
    path is a list of
    (time, lat, lng, alt)
    """
    path, target = find_closest_target(list(path))
    projstr = "+proj=utm +zone={0} +ellps=WGS84".format(target[0])
    if target[1] < 0:
        projstr += " +south"
    proj = pyproj.Proj(projstr)
    r, v, a, r_target = compute_initial_state(path, target, proj)
    r1 = r
    if debug:
        print "target=", target
        print "r_target={0}".format(r_target)
        print "r={r} v={v} a={a}".format(**locals())
    while np.linalg.norm(r - r_target) > THRESHOLD_DISTANCE:
        r, v, a = velocity_verlet(r, v, a, r_target)
        v = velocity_loss(r, v, a, r1, r_target)
        if debug:
            d = np.linalg.norm(r - r_target)
            print "r={r} v={v} a={a}".format(**locals())
        extend_path(path, r, proj)
    return path

def types(reader):
    for (time, lat, lon, alt) in reader:
        yield (int(time), float(lat), float(lon), float(alt))

if __name__ == "__main__":
    uuid = "bb0bdd9a1bffbecee0c8b384a3a9a500a61cebc4"
    import csv
    folder = "/var/www/cusf-standalone-predictor-beta/predict/preds/"+uuid
    with open(folder+"/flight_path.csv") as f:
        reader = csv.reader(f)
        path = list(types(reader))
    print prank_path(path, None, None, True)
