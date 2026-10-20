# Bosch IR Air Conditioner for Home Assistant

Control a **Bosch Climate 3200i** (and likely other Midea-built "Coolix" air conditioners) from Home Assistant through a **Zigbee IR blaster on ZHA**. You get a native `climate` entity with every mode, temperature and fan speed.

There's no code learning: the integration **generates the IR codes itself** from the decoded protocol, so any state can be sent.

- **Modes:** off, cool, heat, dry, fan only, heat/cool (the AC's auto)
- **Temperature:** 17–30 °C in 1 °C steps
- **Fan:** auto, plus fan speeds as percentages (the Bosch remote's own units)
- **Room readings:** current temperature and humidity from any sensors, pre-filled with the IR blaster's own
- **Setup:** entirely in the UI

## What's in this project

```
ha-bosch-ir/
├── README.md
├── hacs.json
├── custom_components/bosch_ir/     # the Home Assistant integration
├── custom_zha_quirks/
│   └── hobeian_zg_ir01.py          # ZHA quirk for the HOBEIAN ZG-IR01 blaster
├── tools/
│   ├── bosch_coolix.py             # command-line IR code generator
│   └── verify_captures.py          # checks the encoder against real captures
└── docs/
    ├── protocol.md                 # the decoded IR protocol
    └── captured_codes.yaml         # nine codes learned from the real remote
```

## Requirements

- Home Assistant **2024.11 or newer**, using **ZHA** for Zigbee. Zigbee2MQTT isn't supported.
- A **Tuya/Zosung-protocol Zigbee IR blaster** with line of sight to the AC's indoor unit. Tested with the **HOBEIAN ZG-IR01**. The TS1201 family (Tuya ZS06, Moes UFO-R11 and similar) uses the same IR clusters and should work. Those already have a quirk built into ZHA, so you can skip step 1.
- An AC that uses the **Midea/Coolix** IR protocol. Tested on a Bosch Climate 3200i. Other Bosch Climate models, Midea, and Midea-built brands probably work too, but haven't been tested. Use `tools/verify_captures.py` to check yours (see [Checking a different AC](#checking-a-different-ac)).

## Installation

### 1. Install the IR blaster quirk (HOBEIAN ZG-IR01 only)

ZHA has no built-in support for the ZG-IR01, and its firmware has a bug that stops sending from working with the standard quirk. This custom quirk fixes both.

1. Copy `custom_zha_quirks/hobeian_zg_ir01.py` to `/config/custom_zha_quirks/` on your Home Assistant.
2. Add this to `configuration.yaml`, unless you already have a custom quirks path:
   ```yaml
   zha:
     custom_quirks_path: /config/custom_zha_quirks/
   ```
3. **Restart Home Assistant fully.** Reloading ZHA isn't enough.
4. Check it worked: open the blaster's device page → ⋮ → *Manage Zigbee device* → *Clusters*. You should see **ZosungIRControl** and **ZosungIRTransmit**. If they still show as plain "Cluster", remove the blaster from ZHA and pair it again.

### 2. Install the integration

**With HACS:**

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/egelmex/ha_bosch_ir`, type **Integration**.
2. Install **Bosch IR Air Conditioner (Coolix)**.
3. Restart Home Assistant.

**Manually:**

1. Copy the `custom_components/bosch_ir/` folder to `/config/custom_components/bosch_ir/`. You can use the File editor or Studio Code Server add-on, Samba, or SSH.
2. Restart Home Assistant.

### 3. Add your AC

1. **Settings → Devices & services → Add integration → Bosch IR.**
2. **Name and IR blaster:** give the AC a name (for example "Living Room AC") and pick the blaster from the list of ZHA devices.
3. **Room sensors and fan speeds:** the blaster's own temperature and humidity sensors are pre-selected, and you can pick others. Choose which fan speeds to offer (default 20/40/60/80/100 %).

The AC appears as its own device, linked to the IR blaster, with an entity such as `climate.living_room_ac`. To change sensors or fan speeds later, use the integration's **Configure** button.

Once it's added, set the entity to match what the AC is actually doing (see [Limitations](#limitations)).

## Using it

It works like any thermostat entity: the climate card, automations, voice assistants and so on.

```yaml
action: climate.set_hvac_mode
target:
  entity_id: climate.living_room_ac
data:
  hvac_mode: heat
---
action: climate.set_temperature
target:
  entity_id: climate.living_room_ac
data:
  temperature: 22
  hvac_mode: cool          # optional: set mode and temperature in one command
---
action: climate.set_fan_mode
target:
  entity_id: climate.living_room_ac
data:
  fan_mode: "60%"
```

Each change sends the complete state (mode, temperature and fan) in one IR command, the same way the physical remote does. `climate.turn_on` restores the last mode you used.

### Sending codes manually

To send a code without the integration, for example from a script or while testing, generate it with the encoder:

```bash
python3 tools/bosch_coolix.py heat 23 60      # mode, °C, fan % (or auto/low/medium/high)
python3 tools/bosch_coolix.py off
python3 tools/bosch_coolix.py --table         # every combination as YAML
```

Then send it through ZHA:

```yaml
action: zha.issue_zigbee_cluster_command
data:
  ieee: "xx:xx:xx:xx:xx:xx:xx:xx"   # your blaster's IEEE address
  endpoint_id: 1
  cluster_id: 57348                 # 0xE004, Zosung IR Control
  cluster_type: in
  command: 2                        # IRSend
  command_type: server
  params:
    code: "<generated code>"
```

## How it works

1. **Encoding.** `coolix.py` builds the IR frames for the requested state (see [`docs/protocol.md`](docs/protocol.md)), converts them to pulse timings, and packs them into the blaster's base64 `key_code` format.
2. **Sending.** The entity calls `zha.issue_zigbee_cluster_command` on the blaster's IR Control cluster. The quirk then transfers the code to the blaster in chunks, and the blaster transmits it.
3. **One command at a time.** The ZG-IR01 firmware can only track one outgoing message, so the entity sends one command at a time with a short gap between them.

## Limitations

- **Assumed state.** IR is one-way: the AC never reports back. The entity shows what it last sent, and restores that after a restart. If someone uses the physical remote, Home Assistant won't know. Setting the entity again re-syncs the AC, because every command carries the complete state.
- **No swing, turbo, sleep, ionizer, display or timer controls yet.** These haven't been decoded from this remote.
- **Following the physical remote isn't supported.** The blaster can only hear IR while in learn mode. Keeping it listening permanently would drain a battery-powered blaster quickly.
- **Shared outdoor units.** If the AC shows `--` after a command, that's a mode conflict, not a problem with this integration: another indoor unit on the same outdoor unit is running in the opposite mode (heat versus cool).

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| The blaster's clusters show as plain "Cluster" | The quirk isn't applied. Check `custom_quirks_path`, restart fully, and re-pair the blaster if needed. |
| *Bosch IR* doesn't appear under Add integration | The files aren't in `/config/custom_components/bosch_ir/`, or Home Assistant hasn't been restarted since. |
| A learned or generated code doesn't do anything | Turn on debug logging (below). If you see `Ignoring IR frame 0x02 for unknown seq 0`, the blaster is using the standard quirk rather than this one. Otherwise check the line of sight to the AC's receiver. |
| The AC beeps, but the wrong mode or temperature is shown | Your AC may use a variant of the protocol. Capture a few codes and run `verify_captures.py`. |

Debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.bosch_ir: debug
    zhaquirks.tuya.ts1201: debug
```

## Checking a different AC

1. Learn a few codes from your remote. On the blaster's device page: *Clusters* → **ZosungIRControl** → *Commands* → `IRLearn` with `on_off: true`, press a button on the remote, then read the attribute `last_learned_ir_code`. Pick states that differ in only one setting, such as two fan speeds at the same temperature.
2. Add them to a YAML file (`name: "<code>"`). Then either list the matching states in `EXPECTED` in `tools/verify_captures.py`, or simply print and compare the decoded frames.
3. Run `python3 tools/verify_captures.py your_codes.yaml`.

If every capture matches, the integration will drive your AC as-is.

## Credits

- The Zosung IR cluster implementation is from [zha-device-handlers](https://github.com/zigpy/zha-device-handlers) (`zhaquirks/tuya/ts1201.py`), itself based on work in zigbee-herdsman-converters.
- Coolix protocol details were cross-checked against the community documentation in IRremoteESP8266.
