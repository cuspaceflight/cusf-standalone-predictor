import math
import os.path
import pyproj
import svg.path
import statsd
from bisect import bisect_left, bisect_right
from utm import from_latlon
from bs4 import BeautifulSoup

DIR = os.path.join(os.path.dirname(__file__), "writing_svg")
CHOICES = ['why_pink.svg', 'whyme.svg', 'oh_no_not_again.svg',
           'help_me.svg', 'vim.svg', 'drawing.svg', 'ohdear.svg']
DESC_CHOICES = ['parachute.svg', 'weeeeeeee.svg', 'hello_ground.svg']

def load_svg(name):
    with open(os.path.join(DIR, name)) as f:
        img = BeautifulSoup(f)

        width = float(img.svg["width"])
        height = float(img.svg["height"])
        data = img.path["d"]

    path = svg.path.parse_path(data)
    path = svg_path_to_points(path)
    path = move_svg_to_origin(path)

    return width, height, path

def svg_path_to_points(path, n=400):
    if len(path) < n:
        return svg_path_to_points_raw(path)
    else:
        return reparametrise_svg_path(path, n)

def svg_path_to_points_raw(path):
    for segment in path:
        assert isinstance(segment, svg.path.Line)
        yield segment.start
    yield segment.end

def move_svg_to_origin(path):
    first = None
    for point in path:
        if first is None:
            first = point
            yield 0j
        else:
            yield point - first

def project_all(path, proj, inverse=False):
    if inverse:
        for z in path:
            lon, lat = proj(z.real, z.imag, inverse=True)
            yield lat, lon
    else:
        for lat, lon in path:
            x, y = proj(lon, lat)
            yield x + y * 1j

def transform(old_path, img):
    width, height, path = img
    old_path = list(old_path)
    n = len(old_path)
    assert n > 1

    for i, z in enumerate(path):
        x, y = z.real, z.imag
        section = x * n / width
        before = int(section)   # round down
        if before >= n - 1:
            before = n - 2
        if before < 0:
            before = 0

        # {source, target} {width, {left, right} {time, x, y, alt}}
        tgl = old_path[before]
        tgr = old_path[before + 1]
        tglx, tgly = tgl.real, tgl.imag
        tgrx, tgry = tgr.real, tgr.imag
        tgw = tgrx - tglx
        sw = width / n
        slx = before * sw

        # new {x, y}
        nx = tglx + (x - slx) * (tgrx - tglx) / sw      # transform
        add_y = (tgw / sw) * y     # scale proportionally
        ny = tgly + (x - slx) * (tgry - tgly) / sw - add_y

        yield nx + ny * 1j

def points_to_svg_path(path):
    last = None
    svg_path = svg.path.Path()
    for point in path:
        if last is not None:
            svg_path.append(svg.path.Line(last, point))
        last = point
    return svg_path

def reparametrise_svg_points_list(path, n):
    path = points_to_svg_path(path)
    return reparametrise_svg_path(path, n)

def reparametrise_svg_path(path, n):
    for i in range(n):
        t = i / float(n - 1)
        yield path.point(t)

def reparametrise(path, n=400):
    # let's borrow svg.path to reparametrise. While checking it out I happened
    # to notice it could do this...
    path = reparametrise_svg_points_list(path, n)
    # check_reparametrisation(path)
    return path

def extract_times_alts(path):
    times = []
    alts = []

    for time, lat, lon, alt in path:
        times.append(time)
        alts.append(alt)

    return times, alts

def drop_times_alts(path):
    for time, lat, lon, alt in path:
        yield lat, lon

def interpolate_times_alts(path, times, alts):
    path = list(path)
    assert len(times) == len(alts)
    n = len(times)
    m = len(path)

    for i, (lat, lon) in enumerate(path):
        interp = float(i) / m * n
        before = int(interp)
        partial = interp - before
        if before >= n - 1:
            yield times[-1], lat, lon, alts[-1]
        else:
            assert before >= 0

            f = lambda s, si, t: s[si] + (s[si + 1] - s[si]) * t
            time = int(f(times, before, partial))
            alt = f(alts, before, partial)

            yield time, lat, lon, alt

def burst_when(path):
    last_alt = None
    for i, (_, _, _, alt) in enumerate(path):
        if last_alt is None:
            last_alt = alt
        if last_alt > alt:
            break
    return i

BURST_BEFORE = 1
BURST_AFTER = 2
BURST_NONE = 3

def split_path(path, burst=BURST_BEFORE, third=True):
    path = list(path)
    burst = burst_when(path)

    start = 0
    end = len(path)
    if burst == BURST_BEFORE:
        end = burst
    elif burst == BURST_AFTER:
        start = burst

    lengths = []
    previous = None

    geod = pyproj.Geod(ellps='WGS84')

    for time, lat, lon, alt in path[start:end]:
        if previous is None:
            length = 0
        else:
            length, plat, plon = previous
            length += geod.inv(plon, plat, lon, lat)[2]
        previous = (length, lat, lon)
        lengths.append(length)

    #print burst, start, end

    if third:
        remove = length / 4.0
        start += bisect_left(lengths, remove)
        end -= len(lengths) - bisect_right(lengths, length - remove)

    #print remove, start, end

    return path[:start], path[start:end], path[end:]

def fix_latlon(path):
    for lat, lon in path:
        lat %= 180
        lon %= 360
        if lat > 90:
            lat -= 180
        if lon > 180:
            lon -= 360
        yield lat, lon

def pick_writing(random):
    name = random.choice(CHOICES + DESC_CHOICES)
    statsd.increment('prank.writing.' + name.replace(".svg", ""))
    return name, name in DESC_CHOICES

def prank_path(path, random, uuid):
    filename, descent = pick_writing(random)
    split_when = BURST_BEFORE
    if descent:
        split_when = BURST_AFTER

    before_prank, path, after_prank = split_path(path, burst=split_when)

    times, alts = extract_times_alts(path)
    path = drop_times_alts(path)
    path = fix_latlon(path)

    path = list(path)
    origin = path[0]
    #print origin
    zone = from_latlon(*origin)[2]
    south = origin[0] < 0
    proj = pyproj.Proj(proj='utm', zone=zone, ellps='WGS84', south=south)

    path = project_all(path, proj)

    path = reparametrise(path)
    img = load_svg(filename)
    path = transform(path, img)

    path = project_all(path, proj, inverse=True)
    path = interpolate_times_alts(path, times, alts)

    path = before_prank + list(path) + after_prank
    return path

# Unused notes; for if I need to implement reparametrisation.
def OLD_intersect(centre, radius, a, b):
    """intersect circle (centre, radius) with line between points a, b"""
    # circle (x - c_x)^2 + (y - c_y)^2 = r^2

    # parametrise line by t:
    # \vect{x} = \vect{a} + (\vect{b} - \vect{a}) t
    # i.e.,   x = a_x + m_x * t   where m_x = b_x - a_x

    a_x, a_y = a
    b_x, b_y = b
    c_x, c_y = centre
    r = radius

    m_x = b_x - a_x
    m_y = b_y - a_y

def OLD_svg_parse():
    assert data[0] == 'm'
    assert data[2] == 'c'

    def point(s):
        x, y = s.split(",")
        return float(x), float(y)

    def add(a, b):
        a_1, a_2 = a
        b_1, b_2 = b
        return (a_1 + b_1, a_2 + b_2)

    # oh; and stuff Beizer curves, let's replace them with straight lines
    # pos = point(data[1])
    pos = (0, 0)
    path = []

    for p in data[3:]:
        pos = add(point(p), pos)
        path.append(pos)

def OLD_svg_complex_to_tuples(path):
    for point in path:
        yield point.real, point.imag

def OLD_tuples_to_svg_complex(path):
    for x, y in path:
        yield x + y * 1j

def OLD_check_reparametrisation(path):
    lx = None
    ly = None
    for rx, ry in path:
        if last is not None:
            print (rx - lx) ** 2 + (ry - ly) ** 2
        lx, ly = rx, ry

def dud_transform(old_path, img):
    width, height, path = img
    old_path = list(old_path)

    ot, ox, oy, oa = old_path[0]
    scale = 100

    for i, (x, y) in enumerate(path):
        yield ot + i, ox + x * scale, oy - y * scale, i
