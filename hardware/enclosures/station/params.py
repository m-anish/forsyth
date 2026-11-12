"""Forsyth station mechanicals: every dimension you are meant to change.

All lengths are millimetres, all angles degrees.

Edit a value here, re-run build.py, and every part regenerates. Values in the
DERIVED section at the bottom are computed; do not edit those. validate() is
run by build.py before any geometry is made and stops the build with a plain
message if a combination cannot work, so a bad tweak fails loudly instead of
producing a subtly broken part.

Sources for the measured numbers are noted inline. "gerber" means read from
the EasyEDA Pro fabrication outputs, "STEP" from hardware/cad/board-a.
"""
import math

# ---------------------------------------------------------------- printer ---
bed_x = 220.0            # Ender-3 V3 KE (from the OrcaSlicer profile in use)
bed_y = 220.0
bed_z = 245.0
bed_margin = 5.0         # keep parts this far inside the bed limits
nozzle = 0.4
layer = 0.2

# ------------------------------------------------- 2020 profile hardware ---
profile = 20.0           # 2020 extrusion, slot 6
m5_clear = 5.5           # clearance hole for M5 into a T-nut
m5_head_d = 9.5          # button head
m5_head_h = 3.0
m5_nut_af = 8.0          # across flats
m5_nut_h = 4.0

# ------------------------------------------------------------- M3 joints ---
m3_clear = 3.4
m3_insert_d = 3.8        # pilot for a brass heat-set insert: its OD minus 0.4
m3_insert_l = 6.0        # insert length (Quartz Components M3 x 6 x 4.2 heat-set)
m3_tap_d = 2.5           # pilot when an M3 screw self-taps into plastic
m3_nut_af = 5.5
m3_nut_h = 2.4

# ---------------------------------------------------------- general fits ---
wall = 2.4               # structural wall, multiple of the nozzle
fit_snug = 0.2           # hand-assembled, no play
fit_slide = 0.3          # drop-in / sliding

# ================================================================= WIND ====
# One housing, vane on top, cups underneath. Each rotor is clamped onto an
# M5 screw that turns in two ball bearings held by the housing.

# -- bearings: set these three to whatever 5 mm-bore bearing you have -------
brg_id = 5.0             # 625ZZ = 5 x 16 x 5.  MR105ZZ = 5 x 10 x 4 (lower drag)
brg_od = 16.0
brg_w = 5.0
brg_fit = 0.10           # added to the pocket diameter; 0.1 = light press
brg_sep = 8.0            # plastic between the two bearings of one rotor
shaft_head_d = 8.5       # M5 socket-head cap screw
shaft_head_h = 5.0
shaft_len = 40.0         # under-head length. Buy PART-threaded (DIN 912: 22 mm of
                         # thread), so the smooth shank is what sits in the bearings
lip_h = 1.0              # rotor lip that touches the bearing inner race only
shim_h = 1.2             # printed ring between the screw head and the bearing
rotor_gap = 0.8          # running clearance, rotor to housing

# -- wind direction PCB (gerber: wind-vane-Gerber_PCB1_2026-07-26) ----------
vane_pcb_d = 60.71       # board outline diameter
vane_pcb_t = 1.6
vane_pcb_hole = 9.15     # centre hole diameter
vane_reed_r = 16.64      # radius of the middle of each radial reed
pcb_edge_grip = 1.8      # how much of the PCB rim the housing clamps
pcb_standoff = 1.8       # gap PCB to lid, room for solder joints

# -- magnets and reeds -------------------------------------------------------
mag_d = 6.0              # disc magnet diameter
mag_t = 2.0              # disc magnet thickness (6 x 2 is what Omrook stocks; 6 x 3 is stronger)
vane_mag_n = 1           # discs stacked for the vane (stood on edge, axis radial)
anemo_mag_n = 1          # discs for the cup rotor
reed_d = 2.4             # reed glass diameter, with a little room
reed_l = 14.5            # reed glass length (14 mm glass; raise to 16.5 for 16 mm)
anemo_mag_r = 18.7       # radius of the anemometer magnet and reed centre

# -- housing ------------------------------------------------------------------
wind_floor = 2.0
wind_lid_t = 2.4
wind_arm_len = 124.0     # rotor axis to the face of the 2020 it bolts to (long enough
                         # that the vane tail swings clear of the sky pod)
wind_rail_w = 7.0        # the arm is two rails so the foot screws stay reachable
wind_rail_h = 10.0
wind_foot_w = 50.0
wind_foot_t = 6.0
wind_foot_pitch_v = 10.0  # +/- from centre, the pair used on a vertical 2020
wind_foot_pitch_h = 12.5  # +/- from centre, the pair used on a horizontal 2020
wind_ear_d = 9.0
wind_ear_angles = (60.0, 180.0, 300.0)
gland_d = 12.5           # PG7 cable gland
gland_flange = 19.0
wind_gasket_t = 0.8      # TPU gasket between the wind housing and its lid
port_gasket_t = 1.0      # TPU washers under connector and gland flanges
wind_gland_angle = 0.0   # 0 = facing the mast, so the cable leaves between the arm rails

# -- cup rotor ----------------------------------------------------------------
n_cups = 3
cup_d = 50.0             # cone mouth diameter
cup_wall = 1.2
cup_rim = 2.0            # stiffening flange round the mouth
cup_arm_r = 55.0         # rotor axis to cup centre
cup_arm_t = 4.0          # arm thickness (tangential in use)
cup_arm_h = 7.0          # arm height (vertical in use)
cup_hub_d = 30.0
cup_key = 4.5            # hook on each arm that locks it into the hub
cup_floor_gap = 4.0      # cup tops pass this far below the housing floor

# -- vane rotor ---------------------------------------------------------------
vane_tail = 130.0        # axis to the tail end
vane_nose = 78.0         # axis to the nose tip
vane_fin_len = 75.0
vane_fin_h = 45.0
vane_fin_t = 2.0
vane_boom = 8.0          # square section of the spine
vane_fin_clear = 3.0     # fin bottom edge above the lid

# ================================================================= RAIN ====
rain_collector_d = 110.0  # inside diameter at the knife edge (95.0 cm2)
rain_wall = 1.6
rain_rim_h = 30.0        # straight wall above the funnel cone (splash guard)
rain_nozzle_d = 5.0
rain_nozzle_len = 6.0
rain_base_t = 3.0
rain_ring_h = 10.0       # upstand on the base that the funnel skirt slips over
rain_foot_r = 20.0       # M5 holes sit on the 45 deg diagonals at this radius

rain_bucket_l = 64.0
rain_bucket_w = 28.0
rain_bucket_floor = 1.2
rain_bucket_wall = 1.2
rain_divider_h = 20.0
rain_end_h = 4.0         # side wall height at the spill ends
rain_tilt = 16.0         # rest angle either side
rain_axle_d = 3.0        # M3 screw or 3 mm rod
rain_pivot_h = 3.5       # axle centre above the bucket floor underside
rain_side_gap = 1.0      # bucket to upright, each side
rain_upright_t = 5.0
rain_stop_x = 18.0       # adjustable stop screws, distance from the pivot
rain_stop_boss_h = 8.0
rain_stop_adj = 3.0      # nominal height of the stop screw head above its boss
# The rain magnet rides on one end of the bucket and passes the reed vertically,
# so it is ~4x further from the reed at rest than in passing. Use a SMALL magnet.
rain_mag_d = 4.0
rain_mag_t = 2.0
rain_mag_x = 26.0        # magnet distance from the pivot, along the bucket
rain_reed_gap = 6.0      # magnet centre to reed axis as they pass

# ============================================================== SCREEN ====
scr_pcb_w = 40.0         # sensor carrier, 4 x 6 cm
scr_pcb_h = 60.0
scr_pcb_t = 1.6
scr_pcb_lift = 8.0       # carrier bottom edge above the base (cable room)
scr_pcb_groove = 2.0     # depth of the rail groove each side
scr_r_in = 31.0          # louvre inner opening radius = sensor chamber radius
scr_r_out = 62.0
scr_pitch = 14.0         # vertical spacing of the louvres
scr_plate_t = 1.2        # louvre thickness, normal to the surface
scr_post_d = 10.0
scr_rod_d = 3.0          # three M3 screws / threaded rods hold the stack
scr_base_t = 3.0
scr_foot_r = 22.0        # M5 holes on the axes at this radius
scr_cable_d = 9.0
scr_n_plates = 0         # 0 = work it out from the carrier height

# =========================================================== ENCLOSURE ====
# Board A rev0 (gerber outline + drill file; STEP for heights).
brd_l = 115.82
brd_w = 44.70
brd_t = 1.6
brd_holes = ((4.445, 15.113), (4.445, 40.132), (111.252, 15.113))  # from lower-left
brd_top_h = 10.5         # tallest part above the top face
brd_bot_h = 2.0          # through-hole leads below the board
sma_y = 26.11            # E220 SMA axis, from the board's connector-row edge
sma_z = 7.1              # SMA axis above the board underside
sma_out = 3.96           # how far the SMA jack stands proud of the board edge (STEP)
brd_slack = 2.0          # board to the left-hand wall
# Antenna: a right-angle stubby that stays INSIDE the box, screwed onto the radio
# and pointing up. ESTIMATED from the product photo - measure yours and correct.
ant_elbow = 14.0         # SMA jack end to the centreline of the whip
ant_d = 12.0             # fattest diameter of the whip
ant_len = 50.0           # whip length, from the SMA centreline to the tip
ant_clear = 4.0          # air between the whip and the side wall
standoff_h = 5.0

# Cell, loose in the box. 32700 = 32.2 x 70.5; for a 32650 set batt_l = 66.
batt_d = 32.5
batt_l = 71.0
batt_end_gap = 6.0       # per end, for tabs and wires

enc_wall = 3.2
enc_back = 3.0
enc_lid_t = 3.0
enc_bay = 34.0           # connector bay height below the board
enc_groove_w = 1.6       # seal groove in the rim; holds the TPU gasket
enc_groove_d = 1.8
gasket_h = 1.4           # TPU lid gasket, as printed
gasket_squeeze = 0.3     # how far the lid's ridge presses into it
enc_tab_shift = 15.0     # mounting tabs sit this far left of centre, which moves
                         # the aluminium mast away from the antenna end of the box
enc_tab_len = 18.0       # mounting tabs
enc_tab_w = 22.0
enc_tab_t = 5.0
enc_lr_tab_y = 28.0      # height of the left/right tab pair

gx16_d = 16.2            # masthead (wind)
gx16_flange = 21.0
gx12_d = 12.2            # solar, rain
gx12_flange = 16.0
# (label, hole diameter, flange/nut diameter). Left to right seen from the front.
enc_ports = (
    ("ENV", gland_d, gland_flange),
    ("PMS", gland_d, gland_flange),
    ("SOLAR", gx12_d, gx12_flange),
    ("RAIN", gx12_d, gx12_flange),
    ("WIND", gx16_d, gx16_flange),
    ("SKY", gx12_d, gx12_flange),      # GX12-4: 1 VBAT, 2 GND, 3 SDA, 4 SCL -> Board A Qwiic
)
enc_port_gap = 3.0       # minimum between neighbouring flanges
# Port names engraved on the lid, above each entry. Skipped if the font is missing.
label_font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
label_h = 4.0            # letter height
label_depth = 0.6

# ================================================================= SKY ====
# MLX90614 on the usual small breakout (GY-906). TYPICAL sizes - measure yours.
sky_pcb_w = 11.5
sky_pcb_l = 17.0
sky_pcb_t = 1.6
sky_can_off = 5.75       # centre of the sensor can from the nearer end of the board
sky_can_d = 8.2          # can diameter
sky_can_h = 4.2          # can height above the board
sky_tilt = 25.0          # sensor axis leans this far from vertical, away from the mast
sky_rise = 65.0          # centre of the opening above the mast top
sky_snout = 8.0          # how deep the can sits below the rim of its cone
sky_snout_half = 40.0    # half-angle of that cone; the 90 deg sensor sees +/-45
sky_can_proud = 1.0      # can stands this far above the cone floor so water runs off it
sky_floor = 1.6
sky_wall = 2.0
sky_plug_h = 8.0
sky_neck = 10.0
sky_foot_w = 45.0
sky_foot_h = 45.0
sky_foot_t = 6.0
sky_foot_pitch = 12.5

# =============================================================== SOLAR ====
panel_l = 100.0          # long side, across the bracket
panel_w = 70.0           # short side, up the slope
panel_t = 3.0
solar_tilt = 20.0        # from horizontal; roughly your latitude
solar_floor = 2.4
solar_rim = 1.6
solar_foot_w = 50.0
solar_foot_t = 6.0
solar_foot_pitch = 12.5

# =============================================================== FRAME ====
# Only used to draw the assembly; cut the real profiles to suit the site.
mast_len = 900.0
arm_len = 420.0
arm_drop = 320.0         # crossarm top face below the mast top
enc_drop = 640.0         # enclosure centre below the mast top


# ============================================================ DERIVED =====
def _derive():
    g = globals()
    g["tower_od"] = brg_od + 2 * wall
    g["tower_h"] = 2 * brg_w + brg_sep
    # Race proportions hold across the common miniature series: the inner race is
    # about 0.27 of (OD - ID) thick, the outer about 0.2. Anything that touches a
    # bearing is sized from these so it lands on one race only.
    span = brg_od - brg_id
    g["race_od"] = brg_id + min(2.6, 0.27 * span)         # sleeve, shim and rotor lip OD
    g["tower_bore"] = brg_od - 0.28 * span                 # shoulder between the pockets
    g["spacer_wall"] = (race_od - (brg_id + 0.3)) / 2
    g["wind_body_h"] = tower_h + 2 * (shaft_head_h + shim_h) + 3.0
    # the vertical screw pair closes up if the housing gets shorter
    g["wind_foot_pv"] = min(wind_foot_pitch_v, wind_body_h / 2 - m5_head_d / 2 - 1.0)
    g["wind_r_pcb"] = vane_pcb_d / 2 + fit_slide          # PCB pocket radius
    g["wind_r_in"] = vane_pcb_d / 2 - pcb_edge_grip       # cavity radius
    g["wind_r_out"] = wind_r_pcb + wall
    g["wind_ear_r"] = wind_r_out + 2.5
    g["wind_lid_r"] = wind_r_out + 2.0
    g["vane_mag_len"] = vane_mag_n * mag_t + 0.2
    g["anemo_mag_len"] = anemo_mag_n * mag_t + 0.2
    g["rotor_flange_h"] = mag_d + 0.3 + 1.2
    g["vane_hub_r"] = tower_od / 2 + 1.5 + wall
    g["vane_flange_r"] = max(vane_reed_r + vane_mag_len / 2 + 2.0, vane_hub_r)
    g["cup_flange_r"] = max(anemo_mag_r + anemo_mag_len / 2 + 2.0, cup_hub_d / 2)
    g["cup_sweep_r"] = cup_arm_r + cup_d / 2 + cup_rim
    g["shaft_len_min"] = shim_h + tower_h + 0.3 + lip_h + 3.5 + m5_nut_h
    g["shaft_in_hub"] = shaft_len - (shim_h + tower_h + 0.3)   # beyond the bearing stack
    g["cup_hub_h"] = max((cup_arm_h + 0.2) + 1.5 + 3.0 + (m5_nut_h + 0.4) + 3.5,
                         cup_d / 2 + cup_rim + cup_floor_gap + cup_arm_h / 2 - lip_h)
    # top of the vane rotor above the wind lid
    hub_top = (tower_h - wind_lid_t) + lip_h + 3.5 + (m5_nut_h + 0.4) + 3.0
    g["vane_top"] = max(hub_top + vane_hub_r - 1.0, vane_fin_clear + vane_fin_h)
    g["vane_hub_top"] = hub_top
    g["vane_bore_top"] = (tower_h - wind_lid_t) + shaft_in_hub + 1.5

    # sky pod
    ts = math.radians(sky_tilt)
    g["sky_rc"] = math.hypot(sky_pcb_l - sky_can_off, sky_pcb_w / 2) + 0.6   # head cavity
    g["sky_r1"] = sky_can_d / 2 + 0.8 + sky_snout * math.tan(math.radians(sky_snout_half))
    g["sky_ro"] = max(sky_rc + sky_wall, sky_r1 + 1.2)
    g["sky_rp"] = sky_rc - 0.15                                             # plug
    g["sky_ring_c"] = sky_can_h - sky_can_proud - sky_floor                 # seal, squeezed
    g["sky_ht"] = 2.0 + sky_plug_h + sky_pcb_t + sky_ring_c + sky_floor + sky_snout
    g["sky_hdr_off"] = sky_pcb_l - sky_can_off - 1.75                       # header from the can
    # plug centre: far enough out that the plug just flattens on the print bed
    g["sky_pod_x"] = sky_rp * math.cos(ts) + (sky_plug_h / 2) * math.sin(ts) - 1.0
    g["sky_zc"] = sky_rise - math.cos(ts) * (sky_ht - 2.0 - sky_plug_h / 2)
    ox = sky_pod_x - (2.0 + sky_plug_h / 2) * math.sin(ts)
    g["sky_head_xmin"] = ox - sky_ro * math.cos(ts)                         # nearest the vane
    g["sky_rim_low"] = sky_rise - sky_ro * math.sin(ts)                     # lowest point of the rim
    g["vane_tip_x"] = vane_tail - wind_arm_len - profile                    # in the pod's frame

    # rain
    t = math.radians(rain_tilt)
    g["rain_r"] = rain_collector_d / 2
    g["rain_pivot_z"] = (rain_base_t + rain_stop_boss_h + rain_stop_adj
                         + rain_stop_x * math.sin(t) + rain_pivot_h * math.cos(t))
    g["rain_nozzle_z"] = rain_pivot_z - rain_pivot_h + rain_divider_h + 3.5
    g["rain_cone_z"] = rain_nozzle_z + rain_nozzle_len
    g["rain_wall_z"] = rain_cone_z + (rain_r - rain_nozzle_d / 2)
    g["rain_top_z"] = rain_wall_z + rain_rim_h
    g["rain_area_cm2"] = math.pi * rain_r ** 2 / 100.0
    g["rain_boss_y"] = 0.6 + rain_mag_d + 0.2            # magnet boss, proud of the bucket side
    g["rain_mag_y"] = rain_bucket_w / 2 + 0.6 + (rain_mag_d + 0.2) / 2
    g["rain_reed_y"] = rain_mag_y + rain_reed_gap
    g["rain_mag_travel"] = rain_mag_x * math.sin(t)       # up/down from the reed, at rest

    # screen
    g["scr_plate_h"] = scr_r_out - scr_r_in               # 45 deg louvre rise
    # 0.8 mm inside the rim: a post exactly tangent to the rim makes a degenerate solid
    g["scr_post_r"] = scr_r_out - scr_post_d / 2 - 0.8
    top = scr_base_t + scr_pcb_lift + scr_pcb_h + 5.0     # carrier top + air
    need = math.ceil((top - scr_base_t - scr_plate_h) / scr_pitch)
    g["scr_plates"] = scr_n_plates if scr_n_plates > 0 else max(3, need)

    # enclosure
    g["ant_bay"] = sma_out + ant_elbow + ant_d / 2 + ant_clear
    g["enc_in_w"] = round(brd_slack + brd_l + ant_bay, 1)
    g["enc_ant_x"] = brd_slack + brd_l + sma_out + ant_elbow      # whip centreline
    g["enc_batt_x"] = brd_slack + brd_l / 2                       # cell sits over the board
    g["enc_tab_x"] = enc_in_w / 2 - enc_tab_shift
    g["enc_in_h"] = round(enc_bay + brd_w + 3.0 + batt_d + 2.4, 1)
    g["enc_in_d"] = round(max(standoff_h + brd_t + brd_top_h + 6.0,
                              batt_d + 3.0), 1)
    g["enc_brd_x"] = brd_slack
    # the box grows upward if the whip is longer than the room above the radio
    g["enc_in_h"] = round(max(enc_in_h, enc_bay + sma_y + ant_len + 3.0), 1)
    g["enc_ant_to_cell"] = (enc_ant_x - ant_d / 2) - (enc_batt_x + batt_l / 2)
    g["enc_ant_to_mast"] = math.hypot((enc_ant_x - ant_d / 2) - (enc_tab_x + profile / 2),
                                      enc_back + standoff_h + sma_z)
    g["enc_brd_y"] = enc_bay
    g["enc_batt_y"] = enc_in_h - batt_d / 2 - 1.2
    g["enc_batt_z"] = batt_d / 2 + 1.0
    g["enc_ports_w"] = sum(p[2] for p in enc_ports) + enc_port_gap * (len(enc_ports) - 1)

    # solar
    g["solar_slope"] = panel_w + 2 * solar_rim + 2 * fit_slide
    g["solar_tray_w"] = panel_l + 2 * solar_rim + 2 * fit_slide
    g["solar_high_y"] = (solar_foot_pitch + m5_head_d / 2 + 2.0
                         + solar_slope * math.sin(math.radians(solar_tilt)))


_derive()


def apply(**overrides):
    """Override parameters by name and recompute the derived values.

    Used for what-if builds: STATION_SET="brg_od=10,brg_w=4" ./build.sh
    """
    g = globals()
    for k, v in overrides.items():
        if k not in g:
            raise KeyError("no such parameter: " + k)
        g[k] = v
    _derive()


def validate():
    """Return a list of human-readable problems; empty means the set is buildable."""
    bad = []

    def need(ok, msg):
        if not ok:
            bad.append(msg)

    for name in ("wall", "cup_wall", "scr_plate_t", "rain_wall", "enc_wall"):
        v = globals()[name]
        need(v >= 2 * nozzle - 1e-9,
             f"{name} = {v} is thinner than two perimeters ({2 * nozzle} mm)")

    # wind
    need(vane_pcb_hole >= shaft_head_d + 0.4,
         "the vane shaft screw head will not pass the PCB centre hole "
         "(vane_pcb_hole vs shaft_head_d)")
    need(shaft_len >= shaft_len_min + 1.0,
         f"shaft_len must be at least {shaft_len_min + 1:.0f} to reach through the hub nut")
    need(vane_bore_top <= vane_top - vane_boom,
         "shaft screw would run up into the vane's spine; shorten shaft_len or raise vane_fin_h")
    need(vane_hub_r - max(0.0, vane_bore_top - vane_hub_top) >= (brg_id + 0.3) / 2 + 1.0,
         "shaft screw breaks out of the vane hub's cone; shorten shaft_len")
    need(cup_hub_h + lip_h - (shaft_in_hub + 1.5) >= cup_arm_h + 0.2 + 1.5,
         "shaft screw reaches the cup-arm slots in the hub; shorten shaft_len")
    need(tower_bore - race_od >= 1.0,
         "bearing too thin in section: the spacer sleeve would rub the tower bore")
    need(spacer_wall >= 0.4,
         "bearing bore too close to the shaft size for any sleeve; use a 5 mm-bore bearing")
    need(wind_arm_len >= cup_sweep_r + 15.0,
         f"cups sweep {cup_sweep_r:.0f} mm; wind_arm_len must be at least "
         f"{cup_sweep_r + 15:.0f} to clear the profile")
    need(vane_tail - vane_fin_len >= wind_ear_r + wind_ear_d / 2 + 6.0,
         "vane fin would strike the lid ears; shorten vane_fin_len or lengthen vane_tail")
    need(vane_reed_r - vane_mag_len / 2 >= tower_od / 2 + 1.5 + 1.2,
         "vane magnet pocket breaks into the hub cavity; use a smaller bearing "
         "or fewer magnets")
    need(anemo_mag_r - reed_l / 2 >= tower_od / 2 + 0.6,
         "anemometer reed would foul the bearing tower; raise anemo_mag_r")
    need(anemo_mag_r + reed_l / 2 <= wind_r_in - 1.5,
         "anemometer reed does not fit inside the housing; lower anemo_mag_r")
    need(cup_hub_d / 2 >= 4.5 + cup_key + 3.0,
         "cup_hub_d too small for the arm hooks")
    if abs(wind_gland_angle) < 1e-6:
        need(gland_flange / 2 + 1.0 <= wind_foot_w / 2 - wind_rail_w,
             "cable gland does not fit between the arm rails; widen wind_foot_w")
    need(wind_foot_pitch_h + m5_head_d / 2 + 0.5 <= wind_foot_w / 2 - wind_rail_w,
         "wind foot: horizontal screw pair collides with the arm rails")
    need(wind_foot_pv >= m5_head_d / 2 + 0.75,
         "wind housing too short for two screws one above the other on the foot")
    need(vane_tail + vane_nose + 6 <= bed_x * math.sqrt(2) - 30,
         "vane rotor is too long for the bed even on the diagonal")

    # sky pod
    need(sky_ring_c >= 1.0,
         "sky pod: no room for a seal round the can; reduce sky_floor or sky_can_proud")
    need(0 <= sky_tilt <= 35, "sky_tilt above 35 deg stops the pod printing cleanly")
    need(sky_head_xmin - vane_tip_x >= 8.0,
         f"vane tail passes {sky_head_xmin - vane_tip_x:.0f} mm from the sky pod; "
         "it needs 8. Lengthen wind_arm_len or shorten vane_tail")
    need(sky_rim_low >= wind_lid_t + wind_gasket_t + vane_top + 2.0,
         "sky pod opening is not above the vane, which would then be in its view; raise sky_rise")

    # rain
    need(rain_bucket_w / 2 + rain_side_gap + rain_upright_t + 3 < rain_r - 4,
         "rain bucket and uprights do not fit inside the collector")
    need(rain_bucket_l / 2 * math.cos(math.radians(rain_tilt)) + 14 < rain_r - 4,
         "rain bucket too long for the collector")
    need(rain_top_z <= bed_z - bed_margin, "rain funnel is taller than the printer")
    gap_min = rain_boss_y - (0.6 + (rain_mag_d + 0.2) / 2) + 1.0 + 1.2 + (reed_d + 0.3) / 2
    need(rain_reed_gap >= gap_min,
         f"rain_reed_gap must be at least {gap_min:.1f} or the reed post rubs the bucket")
    need(rain_mag_x + 3.2 <= rain_bucket_l / 2, "rain_mag_x runs off the end of the bucket")
    need(math.hypot(rain_mag_x + reed_l / 2 + 1, rain_reed_y + 2.6) < rain_r - 3.5,
         "rain reed post does not fit inside the collector")

    # screen
    diag = math.hypot(scr_pcb_w, 14.0)
    need(2 * scr_r_in >= diag + 6.0,
         "sensor chamber too narrow for the carrier; raise scr_r_in")
    need(scr_r_out - scr_r_in >= 1.5 * scr_pitch,
         "louvres do not overlap enough to block sun and rain; "
         "widen the plates or reduce scr_pitch")
    need(2 * scr_r_out <= bed_x - 2 * bed_margin, "screen plates exceed the bed")
    pitch_min = scr_plate_t * math.sqrt(2.0) + (scr_r_out - (scr_post_r - scr_post_d / 2)) + 0.3
    need(scr_pitch >= pitch_min,
         f"scr_pitch must be at least {pitch_min:.1f}: below that each louvre's posts "
         "land on the cone of the louvre underneath")

    # enclosure
    need(enc_ports_w <= enc_in_w - 4.0,
         f"connectors need {enc_ports_w:.0f} mm of the {enc_in_w:.0f} mm bottom wall")
    need(pcb_standoff >= wind_gasket_t + 0.6,
         "pcb_standoff must exceed wind_gasket_t by 0.6 or the vane PCB has no ledge")
    need(enc_groove_d - gasket_h + gasket_squeeze >= 0.4,
         "lid ridge would be under 0.4 mm tall; reduce gasket_h or deepen enc_groove_d")
    need(enc_ant_to_cell >= 15.0,
         f"antenna is only {enc_ant_to_cell:.0f} mm from the cell; it needs 15 mm or it detunes")
    need(enc_batt_x - batt_l / 2 - batt_end_gap >= 1.5,
         "cell and its end gap run into the left wall; shorten batt_end_gap")
    need(batt_l + 2 * batt_end_gap <= enc_in_w - 2.0,
         "cell plus end gaps is longer than the box interior")
    need(enc_in_d >= max(p[2] for p in enc_ports) + 6.0,
         "box is too shallow for the largest connector flange")
    span = enc_in_w + 2 * enc_wall + 2 * enc_tab_len
    need(span <= bed_x - 2 * bed_margin, "enclosure with tabs exceeds the bed width")

    # solar
    need(0 <= solar_tilt <= 40,
         "solar_tilt above 40 deg prints as an overhang; split the bracket instead")
    need(solar_tray_w <= bed_x - 2 * bed_margin, "solar tray exceeds the bed")
    return bad
