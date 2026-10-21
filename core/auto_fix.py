"""One-click Auto-Fix engine for hardware and electrical incompatibilities.
Provides actionable auto-resolve solutions (e.g. inserting level shifters,
Buck converters, Bluetooth modules, or swapping batteries) that transform
incompatibilities into verified PASS statuses on the fly.
"""
import copy
from typing import Dict, List, Any, Optional

AUTO_FIX_CATALOG = {
    "add_level_shifter": {
        "id": "add_level_shifter",
        "rule_ids": ["logic_level"],
        "label": "Add Bi-Directional Logic Level Shifter (₹35)",
        "icon": "⚡",
        "description": "Inserts a 4-channel 3.3V ⇄ 5V bi-directional I2C/GPIO level shifter so 5V sensors safely communicate with 3.3V controllers.",
        "action": "insert",
        "part": {
            "id": "mod_level_shifter",
            "role": "converter",
            "name": "4-Channel Bi-Directional Logic Level Shifter (3.3V-5V)",
            "query": "4 Channel Bi Directional Logic Level Shifter 3.3V 5V",
            "seed_price": 35.0,
            "qty": 1,
            "specs": {"logic_v": 3.3, "out_v": 5.0, "supply_min_v": 3.3, "supply_max_v": 5.0},
            "note": "Translates high/low logic levels bi-directionally between 3.3V and 5V"
        }
    },
    "insert_buck_converter": {
        "id": "insert_buck_converter",
        "rule_ids": ["motor_voltage", "ctrl_vin", "batt_driver_max", "ctrl_fixed_supply"],
        "label": "Insert LM2596 Buck Converter (₹65)",
        "icon": "🔋",
        "description": "Inserts an adjustable DC-DC step-down buck converter (up to 3A) to safely step down high battery voltage (e.g. 11.1V 3S) to 6.0V / 5.0V.",
        "action": "insert",
        "part": {
            "id": "mod_lm2596",
            "role": "power",
            "name": "LM2596 DC-DC Buck Step-Down Converter",
            "query": "LM2596 DC-DC Buck Step-Down Converter module",
            "seed_price": 65.0,
            "qty": 1,
            "specs": {"out_v": 6.0, "max_a": 3.0, "efficiency_pct": 92},
            "note": "Regulates high battery voltages down to safe motor & MCU supply levels"
        }
    },
    "swap_to_2s": {
        "id": "swap_to_2s",
        "rule_ids": ["motor_voltage", "batt_driver_max", "ctrl_vin"],
        "label": "Swap to 2S Li-ion (7.4V)",
        "icon": "🔄",
        "description": "Replaces 3S (11.1V / 12.6V charged) pack with a standard 2S Li-ion (7.4V nominal, 8.4V max) battery pack.",
        "action": "swap",
        "swap_role": "battery",
        "part": {
            "id": "bat_2s",
            "role": "battery",
            "name": "2S Li-ion (7.4V)",
            "query": "2S Li-ion 7.4V battery pack",
            "seed_price": 450.0,
            "qty": 1,
            "specs": {"nominal_v": 7.4, "max_v": 8.4, "capacity_mah": 2200, "weight_g": 90},
            "note": "Standard 2S Li-ion battery pack"
        }
    },
    "add_hc05_bluetooth": {
        "id": "add_hc05_bluetooth",
        "rule_ids": ["bluetooth"],
        "label": "Add HC-05 Bluetooth Module (₹180)",
        "icon": "📶",
        "description": "Inserts an HC-05 UART Bluetooth serial module to give Bluetooth connectivity to controllers like Arduino Nano/Uno.",
        "action": "insert",
        "part": {
            "id": "mod_hc05",
            "role": "comms",
            "name": "HC-05 Bluetooth Serial Module",
            "query": "HC-05 Bluetooth Serial Module",
            "seed_price": 180.0,
            "qty": 1,
            "specs": {"bluetooth": True, "supply_min_v": 3.6, "supply_max_v": 6.0},
            "note": "Provides wireless Bluetooth telemetry & control via serial UART"
        }
    },
    "upgrade_to_esp32": {
        "id": "upgrade_to_esp32",
        "rule_ids": ["bluetooth"],
        "label": "Upgrade to ESP32 DevKit (+₹50)",
        "icon": "🧠",
        "description": "Upgrades the controller from Arduino Nano to ESP32 DevKit with built-in Wi-Fi & Bluetooth.",
        "action": "swap",
        "swap_role": "controller",
        "part": {
            "id": "ctrl_esp32",
            "role": "controller",
            "name": "ESP32 DevKit",
            "query": "ESP32 DevKit DOIT V1",
            "seed_price": 500.0,
            "qty": 1,
            "specs": {"vin_min_v": 5, "vin_max_v": 12, "logic_v": 3.3, "bluetooth": True, "wifi": True, "clock_mhz": 240, "flash_kb": 4096, "sram_kb": 520},
            "note": "Dual-core 240MHz MCU with built-in Wi-Fi and Bluetooth"
        }
    }
}


def get_fixes_for_rule(rule_id: str, parts: Any) -> List[Dict[str, Any]]:
    """Return all available auto-fix options for a given rule violation."""
    fixes = []
    for fix_key, fix in AUTO_FIX_CATALOG.items():
        if rule_id in fix["rule_ids"]:
            if fix_key == "add_level_shifter" and _already_has(parts, "shifter"):
                continue
            if fix_key == "insert_buck_converter" and _already_has(parts, "lm2596"):
                continue
            if fix_key == "swap_to_2s" and _is_2s_battery(parts):
                continue
            if fix_key == "add_hc05_bluetooth" and _already_has(parts, "hc05"):
                continue
            fixes.append(fix)
    return fixes


def apply_auto_fix(parts: Any, fix_id: str) -> Any:
    """Apply the chosen fix to parts (either dict or list), returning the updated build."""
    fix = AUTO_FIX_CATALOG.get(fix_id)
    if not fix:
        return parts

    new_part = copy.deepcopy(fix["part"])

    if isinstance(parts, dict):
        out = copy.deepcopy(parts)
        if fix["action"] == "swap":
            target_role = fix.get("swap_role", new_part["role"])
            out[target_role] = new_part
        else:
            role_key = new_part["role"]
            if role_key in out:
                role_key = f"{role_key}_{new_part['id']}"
            out[role_key] = new_part
        return out

    elif isinstance(parts, list):
        out = copy.deepcopy(parts)
        if fix["action"] == "swap":
            target_role = fix.get("swap_role", new_part["role"])
            replaced = False
            for idx, p in enumerate(out):
                if isinstance(p, dict) and p.get("role") == target_role:
                    out[idx] = new_part
                    replaced = True
                    break
            if not replaced:
                out.append(new_part)
        else:
            out.append(new_part)
        return out

    return parts


def _already_has(parts: Any, keyword: str) -> bool:
    items = parts.values() if isinstance(parts, dict) else parts if isinstance(parts, list) else []
    for p in items:
        if isinstance(p, dict):
            text = (str(p.get("id", "")) + " " + str(p.get("name", "")) + " " + str(p.get("role", ""))).lower()
            if keyword in text:
                return True
    return False


def _is_2s_battery(parts: Any) -> bool:
    items = parts.values() if isinstance(parts, dict) else parts if isinstance(parts, list) else []
    for p in items:
        if isinstance(p, dict) and p.get("role") in ("battery", "power"):
            if "2s" in str(p.get("id", "")).lower() or "2s" in str(p.get("name", "")).lower():
                return True
    return False
