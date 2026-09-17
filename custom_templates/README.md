# Erie Water Treatment — Custom Templates

Ready-to-paste YAML for Home Assistant template sensors, binary sensors, automations, and a Lovelace dashboard.

---

## Quick Start

Add the following includes to your `configuration.yaml`:

```yaml
template:
  - sensor: !include custom_templates/sensors.yaml
  - binary_sensor: !include custom_templates/binary_sensors.yaml

automation: !include_dir_merge_list custom_templates/
```

> **Note:** If you already use `automation: !include automations.yaml`, add
> the Erie automations manually from `automations.yaml` instead.

---

## Energy Dashboard — Water Tracking

The integration automatically provides a sensor that is fully compatible with the **HA Energy Dashboard** water panel.

**Setup steps:**

1. Go to **Settings → Energy → Water** section.
2. Click **Add Water Source**.
3. Search for and select **`sensor.erie_watertreatment_water_consumption`**.
4. Set unit to **Litres (L)**.
5. Save — HA will immediately start tracking hourly/daily/monthly water usage graphs.

> This sensor uses `device_class: water` and `state_class: total_increasing`,
> which are the exact requirements for the HA Energy Dashboard water panel.
> The value is the cumulative litre count from the softener; it never resets.

---

## Entity ID Reference

### Sensors (from Python integration)

| Entity ID | Description |
|---|---|
| `sensor.erie_watertreatment_water_consumption` | Cumulative water use (L) — **Energy Dashboard** |
| `sensor.erie_watertreatment_water_flow_rate` | Instantaneous flow rate (L/h) |
| `sensor.erie_watertreatment_last_regeneration` | Last regeneration ISO timestamp |
| `sensor.erie_watertreatment_nr_regenerations` | Total regeneration count (raw) |
| `sensor.erie_watertreatment_last_maintenance` | Last maintenance ISO date |
| `sensor.erie_watertreatment_total_volume` | Total volume softened (L) |
| `sensor.erie_watertreatment_warnings` | Active warnings as formatted text |
| `sensor.erie_watertreatment_days_since_regeneration` | Days elapsed since last regeneration |
| `sensor.erie_watertreatment_days_since_maintenance` | Days elapsed since last maintenance |
| `sensor.erie_watertreatment_regeneration_count` | Total regeneration count (statistics) |
| `sensor.erie_watertreatment_status_title` | Current status (e.g. "In Service") |
| `sensor.erie_watertreatment_remaining_percentage` | Remaining softening capacity % |
| `sensor.erie_watertreatment_remaining_litres` | Remaining softening capacity (L) |
| `sensor.erie_watertreatment_days_remaining` | Days until next auto-regeneration |

### Binary Sensors (from Python integration)

| Entity ID | Description |
|---|---|
| `binary_sensor.erie_watertreatment_salt_warning` | On when any warning mentions salt (multi-language) |
| `binary_sensor.erie_watertreatment_filter_warning` | On when any warning mentions filter (multi-language) |
| `binary_sensor.erie_watertreatment_service_warning` | On when any warning mentions service/maintenance (multi-language) |
| `binary_sensor.erie_watertreatment_error_warning` | On when any warning mentions error (multi-language) |
| `binary_sensor.erie_watertreatment_any_warning` | On when any warning is active |
| `binary_sensor.erie_watertreatment_holiday_mode` | On when device is in holiday/bypass mode |

### Template Sensors (from sensors.yaml)

| Entity ID | Description |
|---|---|
| `sensor.erie_last_regeneration_formatted` | Human-readable regeneration date/time |
| `sensor.erie_last_maintenance_formatted` | Human-readable maintenance date |
| `sensor.erie_days_since_regeneration` | YAML fallback (integer days since regen) |
| `sensor.erie_days_since_maintenance` | YAML fallback (integer days since maintenance) |
| `sensor.erie_avg_litres_per_day` | Rolling average daily water usage |

### Template Binary Sensors (from binary_sensors.yaml)

| Entity ID | Description |
|---|---|
| `binary_sensor.erie_maintenance_overdue` | On when maintenance > 365 days ago |
| `binary_sensor.erie_high_flow_alert` | On when flow > 500 L/h for 60 s (leak detection) |

---

## Configurable Thresholds

| Threshold | Where to change | Default |
|---|---|---|
| High flow alert | `binary_sensors.yaml` → `flow > 500` | 500 L/h |
| Maintenance overdue | `binary_sensors.yaml` → `days > 365` | 365 days |

---

## Lovelace Dashboard

Copy and paste the YAML below into a new dashboard view (**Settings → Dashboards → Add Dashboard → YAML mode**).

> The `custom:mini-graph-card` requires [mini-graph-card](https://github.com/kalkih/mini-graph-card) from HACS. All other cards use standard HA cards.

```yaml
title: Erie Water Softener
path: erie-water-softener
icon: mdi:water-pump

cards:

  # ── Row 1: Remaining capacity gauges ────────────────────────────────────────
  - type: horizontal-stack
    cards:

      - type: gauge
        entity: sensor.erie_watertreatment_remaining_percentage
        name: Capacity %
        unit: "%"
        min: 0
        max: 100
        needle: true
        severity:
          green: 40
          yellow: 20
          red: 0

      - type: gauge
        entity: sensor.erie_watertreatment_days_remaining
        name: Days Until Regen
        unit: d
        min: 0
        max: 14
        needle: true
        severity:
          green: 5
          yellow: 2
          red: 0

      - type: entity
        entity: sensor.erie_watertreatment_status_title
        name: Status
        icon: mdi:water-pump

  # ── Row 2: Warning status ────────────────────────────────────────────────────
  - type: horizontal-stack
    cards:

      - type: entity
        entity: binary_sensor.erie_watertreatment_salt_warning
        name: Low Salt
        icon: mdi:shaker-outline
        state_color: true

      - type: entity
        entity: binary_sensor.erie_watertreatment_any_warning
        name: Active Warnings
        icon: mdi:alert
        state_color: true

      - type: entity
        entity: binary_sensor.erie_watertreatment_holiday_mode
        name: Holiday Mode
        icon: mdi:beach
        state_color: true

  # ── Row 3: Active warnings (only shown when warnings are active) ─────────────
  - type: conditional
    conditions:
      - entity: binary_sensor.erie_watertreatment_any_warning
        state: "True"
    card:
      type: markdown
      title: ⚠️ Active Warnings
      content: >
        {{ states('sensor.erie_watertreatment_warnings') }}

  # ── Row 4: Detailed status card ──────────────────────────────────────────────
  - type: entities
    title: Softener Status
    show_header_toggle: false
    entities:
      - entity: sensor.erie_watertreatment_remaining_litres
        name: Remaining Capacity (L)
        icon: mdi:water
      - entity: sensor.erie_watertreatment_remaining_percentage
        name: Remaining Capacity (%)
        icon: mdi:percent
      - entity: sensor.erie_watertreatment_days_remaining
        name: Days Until Auto-Regen
        icon: mdi:clock-fast
      - entity: sensor.erie_last_regeneration_formatted
        name: Last Regeneration
        icon: mdi:recycle
      - entity: sensor.erie_watertreatment_days_since_regeneration
        name: Days Since Regeneration
        icon: mdi:clock-outline
      - entity: sensor.erie_watertreatment_regeneration_count
        name: Total Regenerations
        icon: mdi:counter
      - entity: sensor.erie_last_maintenance_formatted
        name: Last Maintenance
        icon: mdi:tools
      - entity: sensor.erie_watertreatment_days_since_maintenance
        name: Days Since Maintenance
        icon: mdi:clock-outline
      - entity: sensor.erie_watertreatment_total_volume
        name: Total Volume Softened (L)
        icon: mdi:database
      - entity: sensor.erie_avg_litres_per_day
        name: Average Daily Usage
        icon: mdi:water-percent

  # ── Row 5: Water consumption history (7 days) ────────────────────────────────
  # This is the same data shown in the HA Energy Dashboard water panel
  - type: history-graph
    title: Water Consumption (7 days)
    hours_to_show: 168
    refresh_interval: 300
    entities:
      - entity: sensor.erie_watertreatment_water_consumption
        name: Cumulative Volume (L)

  # ── Row 6: Flow rate graph (requires mini-graph-card from HACS) ──────────────
  - type: custom:mini-graph-card
    entities:
      - entity: sensor.erie_watertreatment_water_flow_rate
        name: Flow Rate
    name: Water Flow Rate (L/h)
    hours_to_show: 24
    points_per_hour: 6
    smoothing: true
    show:
      extrema: true
      average: true
      icon: true
    color_thresholds:
      - value: 0
        color: "#03a9f4"
      - value: 300
        color: "#f39c12"
      - value: 500
        color: "#e74c3c"

  # ── Row 7: Maintenance overdue alert (only shown when overdue) ───────────────
  - type: conditional
    conditions:
      - entity: binary_sensor.erie_maintenance_overdue
        state: "on"
    card:
      type: markdown
      title: 🔧 Service Required
      content: >
        **⚠️ Maintenance is overdue.**
        Last service: {{ states('sensor.erie_last_maintenance_formatted') }}
        ({{ states('sensor.erie_watertreatment_days_since_maintenance') }} days ago)

  # ── Row 8: All warning binary sensors at a glance ───────────────────────────
  - type: glance
    title: Warning Sensors
    show_state: true
    entities:
      - entity: binary_sensor.erie_watertreatment_salt_warning
        name: Salt
      - entity: binary_sensor.erie_watertreatment_filter_warning
        name: Filter
      - entity: binary_sensor.erie_watertreatment_service_warning
        name: Service
      - entity: binary_sensor.erie_watertreatment_error_warning
        name: Error
      - entity: binary_sensor.erie_watertreatment_any_warning
        name: Any
      - entity: binary_sensor.erie_watertreatment_holiday_mode
        name: Holiday
      - entity: binary_sensor.erie_maintenance_overdue
        name: Maint.
      - entity: binary_sensor.erie_high_flow_alert
        name: High Flow
```
