import sys
import pyproj
import numpy as np

targets = [
    # UTM zone, latitude, longitude, identifier
    (30, 51.4715, -0.4520, "LHR"),
]

ATTRACTOR_MASS = 1E18
REPULSOR_MASS  = 1E16
DT = 10.0 #s
THRESHOLD_DISTANCE = 2000.0 #m

geod = pyproj.Geod(ellps='WGS84')

def find_closest_target(path):
    """Return the path up to the closest point to a target, and that target."""
    target_distances = []
    for point in path:
        for target in targets:
            dist = geod.inv(point[2], point[1], target[2], target[1])[2]
            target_distances.append((dist, target))
    dist, target = min(target_distances[len(path)/4:])
    idx = target_distances.index((dist, target))
    return path[:idx+1], target

G = 6.674E-11
def acceleration(r1, r2):
    """Compute the acceleration due to a mass m at position r2 on object r1"""
    r = r1 - r2
    dist = np.linalg.norm(r)
    r /= dist
    a1 = -r * ((G * ATTRACTOR_MASS) / np.power(dist, 2))
    a2 = +r * ((G * REPULSOR_MASS ) / np.power(dist, 2))
    return a1 + a2

def compute_initial_state(path, target, proj):
    """Return the initial state vector and target position."""
    r_target = np.array(proj(target[2], target[1]))
    r = np.array(proj(path[-1][2], path[-1][1]))
    r_old = np.array(proj(path[-2][2], path[-2][1]))
    v = (r - r_old) / (path[-1][0] - path[-2][0])
    v /= np.linalg.norm(v)
    #v = r - r_target
    #v[0], v[1] = -v[1], v[0]
    #v /= np.linalg.norm(v)
    v *= np.sqrt((G * ATTRACTOR_MASS) / np.linalg.norm(r - r_target))
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
    v *= 0.998
    return v

def prank_path(path, random, uuid):
    """
    path is a list of
    (time, lat, lng, alt)
    """
    path, target = find_closest_target(list(path))
    proj = pyproj.Proj(proj='utm', zone=target[0], ellps='WGS84')
    r, v, a, r_target = compute_initial_state(path, target, proj)
    r1 = r
    #print "r_target={0}".format(r_target)
    #print "r={r} v={v} a={a}".format(**locals())
    while np.linalg.norm(r - r_target) > THRESHOLD_DISTANCE:
        r, v, a = velocity_verlet(r, v, a, r_target)
        v = velocity_loss(r, v, a, r1, r_target)
        d = np.linalg.norm(r - r_target)
        #print "r={r} v={v} a={a}".format(**locals())
        extend_path(path, r, proj)
    return path
