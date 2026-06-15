"""
Global simulation constants and tunable hyper-parameters.

Centralising every magic number here keeps the physics, the AI heuristics and
the dashboard renderer free of inline literals.  Every value carries a unit in
its comment so the mathematical model stays auditable.

All thresholds are expressed in SI-ish units:
    * distance  -> kilometres (km)
    * speed     -> kilometres / hour (km/h)
    * water     -> litres (L)
    * fuel      -> percentage of tank/charge (0-100 %)
    * AQI       -> PM2.5 concentration (micrograms / cubic metre, ug/m3)
    * time      -> a simulation *tick* equals ``TICK_MINUTES`` wall-clock minutes
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Temporal resolution                                                         #
# --------------------------------------------------------------------------- #
TICK_MINUTES: float = 5.0          # one simulation tick == 5 simulated minutes
TICK_HOURS: float = TICK_MINUTES / 60.0

# --------------------------------------------------------------------------- #
# Truck operational thresholds                                                #
# --------------------------------------------------------------------------- #
STUCK_SPEED_KMH: float = 5.0       # below this effective speed => STUCK anomaly
LOW_WATER_FRACTION: float = 0.15   # < 15 % water  => forced replenishment
LOW_FUEL_PCT: float = 20.0         # < 20 % energy => forced refuelling
REPLENISH_TARGET_FRACTION: float = 0.95   # >= 95 % => reintegrate into fleet

# Idle / spray fuel overhead (percentage points burned per tick while the
# misting cannon genset is running but the truck is not translating).
IDLE_BURN_PCT_PER_TICK: float = 0.20
SPRAY_BURN_PCT_PER_TICK: float = 0.45

# --------------------------------------------------------------------------- #
# Air-quality model (CPCB PM2.5 sub-index breakpoints, ug/m3)                 #
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Road-cleaning (dust-suppression) fleet                                      #
# --------------------------------------------------------------------------- #
CLEANER_FLEET_SIZE: int = 10         # dedicated road-washing trucks
DUST_SUPPRESS_PER_TICK: float = 5.0  # ug/m3 settled per cleaning tick, per cell
CLEANER_WATER_PER_TICK: float = 180.0  # litres used washing roads each tick
CLEANER_FUEL_PER_TICK: float = 0.18  # energy burned per cleaning tick (pct)

CRITICAL_PM25: float = 250.0       # hotspot trigger (Very-Poor / Severe border)
CLEARED_PM25: float = 185.0        # mission considered mitigated below this
AQI_INFLUX_COEF: float = 1.7       # ug/m3 added per unit of traffic influx / tick
AQI_AMBIENT_DRIFT: float = 0.9     # passive ug/m3 drift per tick (regional haze)
SPRAY_AQI_PER_LITRE: float = 0.030 # ug/m3 knocked down per litre atomised
STATIONARY_MIST_EFFICIENCY: float = 0.60  # in-gridlock curtain vs. open spraying

# --------------------------------------------------------------------------- #
# Predictive analytics engine                                                 #
# --------------------------------------------------------------------------- #
PREDICT_TRAFFIC_RATIO: float = 1.40   # >40 % rise over two ticks => pre-breach
PREDICT_LOOKBACK_TICKS: int = 2       # compare tick t against tick t-2

# --------------------------------------------------------------------------- #
# Multi-objective Dijkstra cost function                                      #
# --------------------------------------------------------------------------- #
# emission_penalty is only levied when a heavy vehicle would *idle* (high
# traffic factor) through an already-critical AQI cell.  The coefficient maps
# the dimensionless severity product onto an equivalent "cost-hour" overhead so
# it is additive with the travel-time term of W(e).
IDLE_TRAFFIC_FACTOR: float = 2.5      # traffic_density_factor >= this == idling
EMISSION_PENALTY_COEF: float = 0.18   # cost-hours per unit severity product
TRAFFIC_FACTOR_MIN: float = 1.0       # free-flow
TRAFFIC_FACTOR_MAX: float = 12.0      # total blockage (accident / waterlogging)

# --------------------------------------------------------------------------- #
# Dispatcher / workload-splitting heuristics                                  #
# --------------------------------------------------------------------------- #
VREQ_PER_AQI: float = 60.0            # litres required per ug/m3 above threshold
VREQ_MIN: float = 2500.0             # floor for any active mission (L)
VREQ_PREDICTIVE: float = 3500.0      # pre-emptive curtain volume (L)
MAX_SUBFLEET: int = 3                # coordinate at most 2-3 tankers per hotspot
MAX_DISPATCH_ETA_MIN: float = 80.0   # trucks outside this ETA are "out of radius"

# Efficiency-Score weighting (see dispatch.FleetDispatcher.efficiency_matrix).
W_ETA: float = 1.5                   # weight on responsiveness (lower ETA better)
W_VOLUME: float = 2.5                # weight on water coverage of V_req
W_FUEL: float = 0.8                  # weight on remaining energy margin
W_CLASS: float = 0.6                 # weight on tanker capacity-class suitability

# --------------------------------------------------------------------------- #
# Infrastructure (STP / Refuelling) service model                            #
# --------------------------------------------------------------------------- #
DEFAULT_STP_DISPENSE_LPM: float = 3000.0     # recycled-water pumping rate (L/min)
DEFAULT_REFUEL_PCT_PER_MIN: float = 9.0      # CNG fast-fill / charge rate (%/min)
FASTPASS_WATER_RATE_PER_KL: float = 12.0     # mocked micro-transaction (INR / kL)
FASTPASS_FUEL_RATE_PER_PCT: float = 7.5      # mocked micro-transaction (INR / %)
